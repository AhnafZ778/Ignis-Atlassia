"""Private stdio MCP bridge for desktop scientific clients. No public MCP listener."""
from __future__ import annotations
import argparse
from pathlib import Path


def create_server(database,state=None):
    from fastmcp import FastMCP
    from .service import AssistantService
    from .contracts import normalize_context
    service=AssistantService(database,state or Path(database).parent/'assistant/mcp-workspace.sqlite3')
    # One trusted desktop process gets a private workspace; IDs from other sessions
    # are never accepted. Public visitors use the cookie-authenticated HTTP boundary.
    owner=service.store.create_session(normalize_context())
    server=FastMCP('FireAtlas scientific evidence',instructions='Read-only stored NASA observation calculations. Detections are not perimeters or forecasts. Query bounded study context and inspect evidence IDs. No data imports, downloads, shell or human-review signoff.')
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
        return service.capabilities()
    return server,service


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',type=Path,default=Path('data/fireatlas.sqlite3'));args=parser.parse_args()
    server,service=create_server(args.db)
    try:server.run(transport='stdio',show_banner=False)
    finally:service.close()

if __name__=='__main__':main()
