"""Orchestration/portability behavior on isolated synthetic automated fixtures."""
import copy
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
from tests.studio_support import StudioCase
from fireatlas.studio.errors import StudioError, Conflict, NotFound
from fireatlas.studio.portability import read_archive
from fireatlas.studio.orchestration import CONTEXT_SCHEMA

class OrchestrationTests(StudioCase):
    def envelope(self,board=None,instance='test-instance',day='2015-07-01'):
        return {'schema':CONTEXT_SCHEMA,'surface':'studio','origin_instance_id':instance,'origin_tab_id':'tab-'+instance,
                'context_revision':1,'study_selection':{**self.study['context'],'day':day},'active_view':{'operation':'replay','metric':'heatmap','scale':'relative','domain':[0,7], 'temporal_mode':'daily'},
                'selected_object_ids':[], 'result_refs':[], 'destination':{'intent':'append','board_id':board['id'],'revision':board['revision']} if board else {'intent':'new-board'},'return_destination':'investigate.html?year=2015&month=7'}

    def command(self,board=None,key='package'):
        value=self.envelope(board)
        return self.service.commands.submit(self.owner,{'recipe':'visualization_to_investigation','context':value},key,background=False)

    def test_package_retry_and_ack(self):
        result=self.command()
        self.assertEqual(result['status'],'awaiting_view_ack',result)
        did=result['outputs']['document_id']; doc=self.service.get_document(self.owner,did)
        self.assertGreater(len(doc['state']['cards']),4)
        again=self.command();self.assertEqual(again['id'],result['id'])
        self.assertEqual(len(self.service.get_document(self.owner,did)['state']['cards']),len(doc['state']['cards']))
        destination=self.envelope(doc,instance='destination-instance')
        self.service.commands.context(self.owner,destination)
        ack=self.service.commands.action(self.owner,result['id'],'ack',{'instance_id':'destination-instance','document_id':did,'revision':doc['revision'],'object_ids':result['outputs']['object_ids']})
        self.assertEqual(ack['status'],'completed')
        package=self.service.commands.package(self.owner,ack['outputs']['package_id'])
        self.assertEqual(package['source_view']['domain'],[0,7]);self.assertEqual(package['source_view']['scale'],'relative')
        self.assertTrue(self.service.validate_workflow(package['workflow']['definition'])['valid'])

    def test_runnable_output_nodes_insert_new_results_and_prepare_real_export(self):
        command=self.command();did=command['outputs']['document_id'];before=self.service.get_document(self.owner,did)
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            run=self.service.run_workflow(self.owner,command['outputs']['workflow_id'],background=False)
        self.assertEqual(run['status'],'completed',run)
        self.assertEqual(run['outputs']['insert']['type'],'board_result')
        after=self.service.get_document(self.owner,did)
        self.assertEqual(len(after['state']['cards']),len(before['state']['cards'])+2)
        for cid in before['state']['order']:self.assertEqual(before['state']['cards'][cid],after['state']['cards'][cid])
        jid=run['outputs']['export']['job_id']
        import time
        for _ in range(200):
            job=self.service.portability.get(self.owner,jid)
            if job['status'] not in {'queued','preparing'}:break
            time.sleep(.05)
        self.assertEqual(job['status'],'completed',job)
        # Reconciliation of the same command's run must reuse the durable run ID.
        again=self.service.run_workflow(self.owner,command['outputs']['workflow_id'],run_id=run['id'],background=False)
        self.assertEqual(again['id'],run['id']);self.assertEqual(len(self.service.get_document(self.owner,did)['state']['cards']),len(after['state']['cards']))

    def test_one_command_packages_workflow_and_both_portable_exports_without_repeating_science(self):
        body={'recipe':'visualization_to_investigation','context':self.envelope(),'arguments':{'export_formats':['native','excalidraw']}}
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            command=self.service.commands.submit(self.owner,body,'complete-request',background=False)
        self.assertEqual(command['status'],'awaiting_view_ack',command)
        jobs=[self.service.portability.get(self.owner,i) for i in command['outputs']['export_job_ids']]
        self.assertEqual([j['format'] for j in jobs],['native','excalidraw'])
        self.assertTrue(all(j['status']=='completed' for j in jobs))
        with patch.object(self.service.science,'call',side_effect=AssertionError('Idempotent delivery must not recalculate')):
            repeated=self.service.commands.submit(self.owner,body,'complete-request',background=False)
        self.assertEqual(repeated['outputs'],command['outputs'])

    def test_independent_instances_and_stale_context(self):
        self.service.commands.context(self.owner,self.envelope(instance='one'))
        self.service.commands.context(self.owner,self.envelope(instance='two',day='2015-07-02'))
        changed=self.envelope(instance='one',day='2015-07-03')
        with self.assertRaises(Conflict):self.service.commands.context(self.owner,changed)
        changed['context_revision']=2;self.service.commands.context(self.owner,changed)
        with self.service.store.connection() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM studio_contexts').fetchone()[0],2)

    def test_undo_command_preserves_unrelated_edit(self):
        result=self.command();doc=self.service.get_document(self.owner,result['outputs']['document_id'])
        doc=self.add_card(doc,'manual',kind='text',text='Keep this')
        self.service.commands.action(self.owner,result['id'],'undo')
        remaining=self.service.get_document(self.owner,doc['id'])['state']['cards']
        self.assertEqual(list(remaining),['manual'])

    def test_undo_rejects_later_edit_and_cancelled_ack(self):
        result=self.command();doc=self.service.get_document(self.owner,result['outputs']['document_id'])
        self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'update_card','id':doc['state']['order'][0],'patch':{'title':'Manual change'}}]})
        with self.assertRaises(Conflict):self.service.commands.action(self.owner,result['id'],'undo')
        self.service.commands.action(self.owner,result['id'],'cancel')
        with self.assertRaises(Conflict):self.service.commands.action(self.owner,result['id'],'ack',{})

    def test_authorization_and_result_isolation(self):
        board=self.board()
        with self.assertRaises(NotFound):self.service.commands.context(self.other,self.envelope(board))
        document,snap=self.bound_board()
        other=self.board(self.other)
        with self.assertRaises(NotFound):self.service.store.result_for_document(self.other,other['id'],snap['result_id'])

    def test_crash_after_atomic_insertion_and_cancel_before_late_delivery(self):
        original=self.service.commands.update
        def crash(cid,status,*a,**kw):
            if status=='awaiting_view_ack':raise RuntimeError('Simulated loss after atomic board insertion')
            return original(cid,status,*a,**kw)
        with patch.object(self.service.commands,'update',side_effect=crash):result=self.command(key='interrupted')
        self.assertEqual(result['status'],'partial');did=result['outputs']['document_id']
        before=self.service.get_document(self.owner,did)
        self.service.commands.start(self.owner,result['id'],background=False)
        after=self.service.get_document(self.owner,did)
        self.assertEqual(before['state'],after['state']);self.assertEqual(before['revision'],after['revision'])
        self.assertEqual(self.service.commands.get(self.owner,result['id'])['status'],'awaiting_view_ack')
        with patch.object(self.service.commands,'start'):
            pending=self.command(key='cancel-before-start')
        self.service.commands.action(self.owner,pending['id'],'cancel')
        self.service.commands.start(self.owner,pending['id'],background=False)
        self.assertEqual(self.service.commands.get(self.owner,pending['id'])['outputs'],{})
        with self.assertRaises(StudioError):self.service.commands.submit(self.owner,{'recipe':'continue_investigation','context':self.envelope(),'arguments':{'action':'execute_sql'}},'invalid')

    def test_restart_reconcile_saved_insertion(self):
        result=self.command()
        from fireatlas.studio.orchestration import Commands
        manager=Commands(self.service)
        manager.start(self.owner,result['id'],background=False)
        doc=self.service.get_document(self.owner,result['outputs']['document_id'])
        self.assertEqual(len(doc['state']['cards']),len(result['outputs']['object_ids']))
        self.assertEqual(manager.get(self.owner,result['id'])['status'],'awaiting_view_ack')

class PortabilityTests(StudioCase):
    def test_export_retry_reuses_saved_revision_and_rejects_another_intent(self):
        doc=self.add_card(self.board(),'note',kind='text',text='Frozen first revision')
        body={'format':'svg','revision':doc['revision']}
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,doc['id'],body,'stable-export',background=False)
        self.assertEqual(job['status'],'completed',job)
        self.add_card(doc,'later',kind='text',text='Keep this later work')
        with patch.object(self.service.portability,'capture',side_effect=AssertionError('A repeated export must not recapture')):
            repeated=self.service.portability.submit(self.owner,doc['id'],body,'stable-export',background=False)
        self.assertEqual(repeated['id'],job['id'])
        with self.assertRaises(Conflict):self.service.portability.submit(self.owner,doc['id'],{'format':'native'},'stable-export',background=False)

    def test_restored_story_retains_historical_scenes_and_remapped_references(self):
        doc,snapshot=self.bound_board(operation='replay',kind='map')
        saved=self.service.create_story(self.owner,doc['id'],{'title':'Frozen study story'})
        resolved=self.service.resolve_story(self.owner,saved['id'])['resolved']
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,doc['id'],{'format':'native'},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id']);restored=self.service.portability.restore(self.other,path)
        restored_story=self.service.get_story(self.other,restored['id_map'][saved['id']])
        self.assertEqual(len(restored_story['imported_frozen_scenes']),len(resolved['scenes']))
        with patch.object(self.service.science,'call',side_effect=AssertionError('Frozen restoration must not call science')):
            bundle,_=self.service.portability.capture(self.other,restored['document']['id'])
        self.assertEqual(bundle['stories'][0]['frozen_scenes'],restored_story['imported_frozen_scenes'])
        for before,after in zip(resolved['scenes'],restored_story['imported_frozen_scenes']):
            self.assertEqual(after['chapter_id'],restored['id_map'][before['chapter_id']])
            self.assertEqual(after['visual_svg'],before['visual_svg'])

    def test_whole_board_native_restore_and_excalidraw_structure(self):
        doc,snap=self.bound_board(operation='replay',kind='map')
        doc=self.add_card(doc,'offscreen',kind='text',text='editable note',transform={'x':12000,'y':9000,'w':380,'h':240})
        self.service.save_workflow(self.owner,doc['id'],{'nodes':[{'id':'input','type':'evidence_input','params':{'snapshot_id':snap['id']}}]})
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):job=self.service.portability.submit(self.owner,doc['id'],{'format':'native','revision':doc['revision']},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        bundle,_=read_archive(path)
        self.assertIn('offscreen',bundle['board']['cards'])
        with zipfile.ZipFile(path) as z:
            scene=json.loads(z.read('interop/board.excalidraw'))
            self.assertEqual(scene['type'],'excalidraw')
            self.assertGreater(len(scene['elements']),len(doc['state']['cards']))
            self.assertTrue(scene['files']);self.assertTrue(any(e['type']=='text' for e in scene['elements']))
        imported=self.service.portability.restore(self.other,path)
        restored=imported['document'];self.assertEqual(len(restored['state']['cards']),2)
        self.assertNotEqual(restored['id'],doc['id']);self.assertTrue(set(restored['state']['cards']).isdisjoint(doc['state']['cards']))
        new_snap=next(iter(restored['snapshots'].values()))
        self.assertEqual(new_snap['receipt_sha256'],snap['receipt_sha256'])
        self.assertTrue(self.service.snapshot_report(self.other,restored['id'],new_snap['id'])['verification']['verified'])

    def test_frame_scope_and_rehashed_semantic_tampering(self):
        import hashlib
        doc,snap=self.bound_board(operation='replay',kind='map');doc=self.add_card(doc,'c2',kind='text',text='In frame');doc=self.add_card(doc,'outside',kind='text',text='Excluded')
        doc=self.service.transact(self.owner,doc['id'],{'base_revision':doc['revision'],'ops':[{'op':'set_group','group':{'id':'g1','title':'Selected evidence','card_ids':['c1','c2']}}]})
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,doc['id'],{'format':'native','scope':{'kind':'frame','frame_id':'g1'}},background=False)
        self.assertEqual(job['status'],'completed',job);path,_=self.service.portability.download(self.owner,job['id'])
        bundle,_=read_archive(path);self.assertEqual(set(bundle['board']['cards']),{'c1','c2'})
        with zipfile.ZipFile(path) as archive:files={n:archive.read(n) for n in archive.namelist()}
        snapshots=json.loads(files['snapshots.json']);saved=next(iter(snapshots.values()));saved['facts'][0]['value']=999999
        from fireatlas.studio.store import dumps,sha256_text
        saved['snapshot_sha256']=sha256_text(dumps({k:v for k,v in saved.items() if k!='snapshot_sha256'}))
        files['snapshots.json']=dumps(snapshots).encode();manifest=json.loads(files['manifest.json'])
        manifest['files']['snapshots.json']={'bytes':len(files['snapshots.json']),'sha256':hashlib.sha256(files['snapshots.json']).hexdigest()}
        manifest['expanded_bytes']=sum(len(v) for k,v in files.items() if k!='manifest.json');files['manifest.json']=dumps(manifest).encode()
        tampered=self.root/'tampered.zip'
        with zipfile.ZipFile(tampered,'w') as archive:
            for name,data in files.items():archive.writestr(name,data)
        with self.assertRaises(StudioError):self.service.portability.restore(self.other,tampered)

    def test_archive_rejects_traversal_and_duplicates(self):
        for names in (['../board.json'],['board.json','board.json']):
            path=self.root/'unsafe.zip'
            with zipfile.ZipFile(path,'w') as z:
                for name in names:z.writestr(name,b'{}')
            with self.assertRaises(StudioError):read_archive(path)

    def test_rehashed_archive_rejects_false_image_metadata(self):
        import base64,hashlib
        from fireatlas.studio.store import dumps
        doc=self.board()
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j7XcAAAAASUVORK5CYII=')
        asset=self.service.add_asset(self.owner,doc['id'],png,'Test fixture','Automated fixture')
        doc=self.add_card(doc,'image',kind='image',asset_id=asset['id'])
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):
            job=self.service.portability.submit(self.owner,doc['id'],{'format':'native'},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id'])
        with zipfile.ZipFile(path) as z:files={n:z.read(n) for n in z.namelist()}
        assets=json.loads(files['assets.json']);assets[0]['sha256']='0'*64;files['assets.json']=dumps(assets).encode()
        manifest=json.loads(files['manifest.json']);manifest['files']['assets.json']={'bytes':len(files['assets.json']),'sha256':hashlib.sha256(files['assets.json']).hexdigest()}
        manifest['expanded_bytes']=sum(len(v) for k,v in files.items() if k!='manifest.json');files['manifest.json']=dumps(manifest).encode()
        modified=self.root/'false-image-metadata.zip'
        with zipfile.ZipFile(modified,'w') as z:
            for name,data in files.items():z.writestr(name,data)
        with self.assertRaisesRegex(StudioError,'asset metadata'):self.service.portability.restore(self.other,modified)

    def test_bitmap_and_pdf_export_work_with_a_relative_service_root(self):
        import os
        from fireatlas.studio.portability import Portability,browser_path
        if not browser_path():self.skipTest('Local Chromium unavailable')
        self.service.root=Path(os.path.relpath(self.service.root,Path.cwd()))
        self.service.portability=Portability(self.service)
        doc=self.add_card(self.board(),'note',kind='text',text='UTC evidence retained')
        for fmt,magic in [('png',b'\x89PNG'),('pdf',b'%PDF')]:
            with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):job=self.service.portability.submit(self.owner,doc['id'],{'format':fmt},background=False)
            self.assertEqual(job['status'],'completed',job)
            path,_=self.service.portability.download(self.owner,job['id']);self.assertTrue(path.read_bytes().startswith(magic))

    def test_revision_and_offscreen_svg(self):
        doc=self.board();doc=self.add_card(doc,'note',kind='text',text='whole board',transform={'x':2000,'y':3000,'w':400,'h':240})
        with self.assertRaises(Conflict):self.service.portability.capture(self.owner,doc['id'],1)
        with patch('fireatlas.studio.portability.StorageBudget.check',return_value={}):job=self.service.portability.submit(self.owner,doc['id'],{'format':'svg'},background=False)
        self.assertEqual(job['status'],'completed',job)
        path,_=self.service.portability.download(self.owner,job['id']);self.assertIn('whole board',path.read_text())
