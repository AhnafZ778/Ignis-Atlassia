"""Private stdio MCP bridge for desktop scientific clients. No public MCP listener."""
from __future__ import annotations
import argparse
from pathlib import Path
try:
    from fastmcp import Context
except ImportError:
    Context = None

STUDIO_UI_URI = "ui://fireatlas/studio/app.html"
STUDIO_UI_EXTENSION = "io.modelcontextprotocol/ui"


def create_server(database,state=None):
    from fastmcp import FastMCP
    from .service import AssistantService
    from .contracts import normalize_context
    from ..studio.service import StudioService
    service=AssistantService(database,state or Path(database).parent/'assistant/mcp-workspace.sqlite3')
    studio=StudioService(database, root=Path(database).parent/'assistant/mcp-studio', assistant=service)
    service.studio = studio
    studio_owner, _token = studio.store.create_principal()
    # One trusted desktop process gets a private workspace; IDs from other sessions
    # are never accepted. Public visitors use the cookie-authenticated HTTP boundary.
    owner=service.store.create_session(normalize_context())
    server=FastMCP('FireAtlas scientific evidence',instructions='Read-only stored NASA observation calculations plus private Research Studio authoring. Detections are not perimeters or forecasts. Studio actions create boards and stories whose values still come from checked scientific resolvers. No data imports, downloads, shell or human-review signoff.')
    @server.tool(annotations={'readOnlyHint':True,'destructiveHint':False},timeout=120)
    def investigate(operation:str,context:dict,arguments:dict|None=None)->dict:
        """Run an authoritative scientific method, returning values, source status and a result hash."""
        return service.science.call(owner,operation,context,arguments)
    @server.tool(annotations={'readOnlyHint':True,'destructiveHint':False})
    def get_evidence(result_id:str)->dict:
        """Read full evidence from this desktop workspace only."""
        return service.store.get_artifact(owner,result_id,'evidence')
    @server.tool(annotations={'readOnlyHint':True,'destructiveHint':False})
    def describe_capabilities()->dict:
        """Methods, supported regions and scientific limitations."""
        return {**service.capabilities(), "studio": studio.capabilities()}
    @server.tool(annotations={'readOnlyHint':False,'destructiveHint':False})
    def studio_build_investigation(title:str="MCP investigation",context:dict|None=None)->dict:
        """Create a private deterministic Studio board from a scientific study context."""
        document = studio.create_document(studio_owner, {"title": title, "study": {"context": context or {}}})
        return studio.presentation_action(studio_owner, document["id"], {"action": "build_investigation", "base_revision": document["revision"]})
    @server.tool(annotations={'readOnlyHint':True,'destructiveHint':False})
    def studio_get_document(document_id:str)->dict:
        """Read a private Studio board created by this MCP process."""
        return studio.get_document(studio_owner, document_id)
    @server.tool(annotations={'readOnlyHint':False,'destructiveHint':False})
    def studio_create_story(document_id:str)->dict:
        """Create a six-chapter checked story draft from a private Studio board."""
        return studio.presentation_action(studio_owner, document_id, {"action": "create_story_draft", "story": {}})
    @server.tool(annotations={'readOnlyHint':False,'destructiveHint':False})
    def studio_register_context(context:dict)->dict:
        """Register this MCP host/app instance's owned study selection. Instance IDs do not authorize other users' boards."""
        if context.get('surface')!='mcp': raise ValueError('Use the MCP context surface.')
        return studio.commands.context(studio_owner,context)
    @server.tool(annotations={'readOnlyHint':False,'destructiveHint':False})
    def studio_command(recipe:str,context:dict,idempotency_key:str,arguments:dict|None=None)->dict:
        """Execute the same registered deterministic packaging/continuation/export recipe used by the website. Saving is distinct from host view acknowledgment."""
        if context.get('surface')!='mcp': raise ValueError('Capture an MCP host/app selection.')
        return studio.commands.submit(studio_owner,{'recipe':recipe,'context':context,'arguments':arguments or {}},idempotency_key,assistant_owner=owner)
    @server.tool(annotations={'readOnlyHint':True,'destructiveHint':False})
    def studio_command_status(command_id:str)->dict:
        """Read persisted recipe steps, saved objects, omissions and recovery actions."""
        return studio.commands.get(studio_owner,command_id)
    @server.tool(annotations={'readOnlyHint':False,'destructiveHint':False})
    def studio_command_action(command_id:str,action:str,arguments:dict|None=None)->dict:
        """Cancel, resume, undo or acknowledge a command from the actual registered MCP destination instance."""
        return studio.commands.action(studio_owner,command_id,action,arguments)
    @server.tool(annotations={'readOnlyHint':False,'destructiveHint':False})
    def studio_export_board(document_id:str,revision:int,format:str='native')->dict:
        """Prepare the whole saved board, including offscreen objects, with frozen evidence and local portability helpers. No remote transfer."""
        return studio.portability.submit(studio_owner,document_id,{'revision':revision,'format':format})
    @server.tool(annotations={'readOnlyHint':True,'destructiveHint':False})
    def studio_export_status(export_id:str)->dict:
        """Read preparation status. HTTP download paths do not authenticate an MCP host; use the owned chunk tool."""
        result=studio.portability.get(studio_owner,export_id);result.pop('download',None);return result
    @server.tool(annotations={'readOnlyHint':True,'destructiveHint':False})
    def studio_export_chunk(export_id:str,offset:int=0)->dict:
        """Read at most 1 MiB of a completed owned archive for host-local download; no arbitrary filesystem access."""
        import base64
        if type(offset)!=int or offset<0: raise ValueError('Use a nonnegative byte offset.')
        path,mime=studio.portability.download(studio_owner,export_id)
        with path.open('rb') as source: source.seek(offset);data=source.read(1024*1024)
        return {'mime':mime,'offset':offset,'total_bytes':path.stat().st_size,'data':base64.b64encode(data).decode(),'next_offset':offset+len(data)}
    ui_file = Path(__file__).resolve().parents[1] / 'static/studio-mcp/index.html'
    if ui_file.is_file():
        @server.resource(STUDIO_UI_URI, mime_type='text/html;profile=mcp-app',
                         app={'csp': {'connectDomains': [], 'resourceDomains': []}, 'prefersBorder': True})
        def studio_app_resource() -> str:
            """Self-contained SDK view: no credentials, owner tokens, external code or imagery."""
            return ui_file.read_text()

        @server.tool(app={'resourceUri': STUDIO_UI_URI}, annotations={'readOnlyHint': True, 'destructiveHint': False})
        def studio_open_board(document_id: str, ctx: Context) -> dict:
            """Open an owned compact Studio board in MCP Apps, or return its structured/text evidence in a conventional client."""
            document = studio.get_document(studio_owner, document_id)
            projects = studio.document_projects(studio_owner, document_id)
            negotiated = ctx.client_supports_extension(STUDIO_UI_EXTENSION)
            return {'document': document, 'stories': projects['stories'], 'ui': {'negotiated': negotiated, 'resource_uri': STUDIO_UI_URI if negotiated else None,
                    'fallback': 'This client can inspect the same board and checked values as text and JSON.'}}

        @server.tool(app={'resourceUri': STUDIO_UI_URI}, annotations={'readOnlyHint': True, 'destructiveHint': False})
        def studio_preview_card(document_id: str, card_id: str) -> dict:
            """Prepare a bounded schematic for a card owned by this desktop session."""
            document = studio.get_document(studio_owner, document_id)
            card = document['state']['cards'].get(card_id)
            if not card or not card.get('snapshot_id'):
                raise ValueError('Choose a frozen evidence card from this board.')
            return studio.snapshot_preview(studio_owner, document_id, card['snapshot_id'], card['type'])

        @server.tool(app={'resourceUri': STUDIO_UI_URI}, annotations={'readOnlyHint': True, 'destructiveHint': False})
        def studio_read_story(story_id: str, revision: int | None = None) -> dict:
            """Read an immutable resolved story revision owned by this desktop session."""
            value = studio.get_story(studio_owner, story_id, revision)
            if not value.get('resolved'):
                raise ValueError('This story is a draft. Freeze its evidence and resolve its scenes before reading.')
            return value
    return server,service


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',type=Path,default=Path('data/fireatlas.sqlite3'));args=parser.parse_args()
    server,service=create_server(args.db)
    try:server.run(transport='stdio',show_banner=False)
    finally:
        service.close()
        service.studio.close()

if __name__=='__main__':main()
