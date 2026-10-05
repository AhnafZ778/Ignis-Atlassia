"""MCP Apps negotiation and ordinary text/JSON clients share the same owned evidence."""
import asyncio
import unittest
try:
    from studio_support import StudioCase
except ImportError:
    from .studio_support import StudioCase

try:
    from fastmcp import Client
    from mcp.client.extension import ClientExtension
except ImportError:
    Client = None


@unittest.skipIf(Client is None, 'Optional FastMCP runtime is not installed')
class StudioMCPTests(StudioCase):
    def test_negotiated_resource_and_text_fallback(self):
        from fireatlas.assistant.mcp_server import create_server, STUDIO_UI_URI, STUDIO_UI_EXTENSION
        class Apps(ClientExtension):
            identifier = STUDIO_UI_EXTENSION
        server, service = create_server(self.database, self.root / 'mcp-assistant.sqlite3')
        self.addCleanup(service.close)
        self.addCleanup(service.studio.close)
        async def exercise():
            async with Client(server) as plain:
                tools = await plain.list_tools()
                by_name = {t.name: t for t in tools}
                self.assertEqual(by_name['studio_open_board'].meta['ui']['resourceUri'], STUDIO_UI_URI)
                created = (await plain.call_tool('studio_build_investigation', {'context': self.study['context']})).data
                document = created['document']
                fallback = (await plain.call_tool('studio_open_board', {'document_id': document['id']})).data
                self.assertFalse(fallback['ui']['negotiated'])
                self.assertIsNone(fallback['ui']['resource_uri'])
                self.assertTrue(fallback['document']['state']['cards'])
                # IDs from a different private principal are not accepted by this process.
                foreign = self.service.create_document(self.owner, {'title': 'Private'})
                with self.assertRaises(Exception):
                    await plain.call_tool('studio_open_board', {'document_id': foreign['id']})
            async with Client(server, extensions=[Apps()]) as rich:
                opened = (await rich.call_tool('studio_open_board', {'document_id': document['id']})).data
                self.assertTrue(opened['ui']['negotiated'])
                resource = await rich.read_resource(STUDIO_UI_URI)
                self.assertEqual(resource[0].mime_type, 'text/html;profile=mcp-app')
                self.assertIn('FireAtlas', resource[0].text)
                self.assertNotIn('LIVEBLOCKS_SECRET_KEY', resource[0].text)
                self.assertIn('updateModelContext', resource[0].text)
        asyncio.run(exercise())
