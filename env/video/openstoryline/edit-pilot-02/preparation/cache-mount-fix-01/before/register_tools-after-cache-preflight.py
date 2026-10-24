from __future__ import annotations
from dataclasses import asdict
from typing import Annotated
from pydantic import BaseModel, Field
import inspect
import traceback
from pathlib import Path

from open_storyline.config import Settings
from open_storyline.skills.skills_io import dump_skills
from open_storyline.utils.register import NODE_REGISTRY

from open_storyline.mcp.sampling_requester import make_llm
from open_storyline.nodes.core_nodes.base_node import BaseNode
from open_storyline.nodes.node_summary import NodeSummary
from open_storyline.nodes.node_state import NodeState
from src.open_storyline.storage.agent_memory import ArtifactStore

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

def create_tool_wrapper(node: BaseNode, input_schema: type[BaseModel], cfg: Settings,
                        kind_to_node_id: dict[str, str] | None = None):
    """
    Factory function: Convert custom Node to MCP Tool function
    """
    # Get metadata for @server.tool parameters
    meta = node.meta if hasattr(node, 'meta') else None

    async def wrapper(mcp_ctx: Context, **kwargs) -> dict:
        # 1. Unified handling of context and Session
        request = mcp_ctx.request_context.request
        headers = request.headers
        session_id = headers.get('X-Storyline-Session-Id')
        
        # 2. Session lifecycle management
        session_manager = mcp_ctx.request_context.lifespan_context
        if hasattr(session_manager, 'cleanup_expired_sessions'):
            session_manager.cleanup_expired_sessions(session_id)

        # 3. Construct parameters
        # Note: FastMCP automatically injects parameters into kwargs, merge them here
        req_json = await request.json()
        params = kwargs.copy()
        params.update(req_json.get('params', {}).get('arguments', {}))

        # `inputs` is an internal media payload added by the LangChain-side
        # interceptor; it is intentionally absent from LoadMediaInput's public
        # MCP schema. FastMCP validates arguments against that schema and drops
        # the extra field before invoking this wrapper, so reconstruct it from
        # the configured local media directory at the server boundary.
        if getattr(meta, 'node_id', None) == 'load_media' and not params.get('inputs'):
            media_dir = Path(cfg.project.media_dir)
            media_exts = {'.mp4', '.mov', '.mkv', '.avi', '.jpg', '.jpeg',
                          '.png', '.webp', '.bmp'}
            inputs = []
            if media_dir.is_dir():
                from open_storyline.mcp.hooks.node_interceptors import should_inline_media_as_base64
                inline_media = should_inline_media_as_base64(cfg)
                for media_path in sorted(media_dir.iterdir()):
                    if not media_path.is_file() or media_path.suffix.lower() not in media_exts:
                        continue
                    absolute_path = str(media_path.resolve())
                    if inline_media:
                        from open_storyline.storage.file import FileCompressor
                        compressed = FileCompressor.compress_and_encode(absolute_path)
                        inputs.append({'path': absolute_path,
                                       'base64': compressed.base64,
                                       'md5': compressed.md5,
                                       'orig_path': absolute_path,
                                       'orig_md5': compressed.md5})
                    else:
                        inputs.append({'path': absolute_path,
                                       'orig_path': absolute_path,
                                       'orig_md5': None})
            params['inputs'] = inputs

        elif session_id:
            # The LangChain interceptor also injects prerequisite artifacts,
            # but those internal fields are outside each public MCP schema and
            # FastMCP drops them during argument validation. Rehydrate only
            # artifacts from this session at the server boundary.
            required_kinds = (node.meta.default_require_prior_kind
                              if params.get('mode', 'auto') != 'auto'
                              else node.meta.require_prior_kind)
            if required_kinds:
                _store = ArtifactStore(artifacts_dir=cfg.project.outputs_dir,
                                       session_id=session_id)
                for kind in required_kinds:
                    source_node_id = (kind_to_node_id or {}).get(kind, kind)
                    prior_meta = _store.get_latest_meta(node_id=source_node_id,
                                                        session_id=session_id)
                    if prior_meta is None:
                        continue
                    _, prior_output = _store.load_result(prior_meta.artifact_id)
                    if isinstance(prior_output, dict) and isinstance(prior_output.get('payload'), dict):
                        params[kind] = prior_output['payload']

        # artifact_id is not part of any node's input schema, so agents
        # cannot pass it; generate one per call exactly like the upstream
        # read_node_history / write_skills wrappers do (OPENSTORYLINE-
        # EDIT-PILOT-01 wiring fix; upstream hard-keyed params['artifact_id']
        # which always raises KeyError through the MCP schema path).
        artifact_id = params.get('artifact_id')
        if not artifact_id:
            from open_storyline.storage.agent_memory import ArtifactStore as _AS
            _store = _AS(artifacts_dir=Path(cfg.project.outputs_dir) / ".server_cache",
                         session_id=session_id)
            artifact_id = _store.generate_artifact_id(
                (req_json.get('params', {}) or {}).get('name', 'node'))
        node_state = NodeState(
            session_id=session_id,
            artifact_id=artifact_id,
            lang=params.get('lang', 'zh'),
            node_summary=NodeSummary(),
            llm=make_llm(mcp_ctx),
            mcp_ctx=mcp_ctx,
        )
        result = await node(node_state, **params)
        return result


    new_params = []
    # First parameter is fixed as mcp_ctx
    new_params.append(
        inspect.Parameter(
            'mcp_ctx', 
            inspect.Parameter.POSITIONAL_OR_KEYWORD, 
            annotation=Context
        )
    )

    new_annotations = {'mcp_ctx': Context}

    if input_schema:
        for field_name, field_info in input_schema.model_fields.items():
            # Use Annotated to carry description, FastMCP will recognize it as JSON Schema description
            annotation = Annotated[field_info.annotation, field_info]
            
            new_params.append(
                inspect.Parameter(
                    field_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=field_info.default if field_info.default is not ... else inspect.Parameter.empty,
                    annotation=annotation
                )
            )
            new_annotations[field_name] = annotation

    wrapper.__name__ = meta.name
    wrapper.__doc__ = meta.description
    wrapper.__signature__ = inspect.Signature(new_params)
    wrapper.__annotations__ = new_annotations
    
    return wrapper, meta


def register(server: FastMCP, cfg: Settings) -> None:
    # Task overlay: import only native nodes used by the speech rough-cut path.
    # The upstream package scan eagerly imports optional TTS, retrieval,
    # transition-generation and vision nodes, pulling unrelated dependencies.
    from open_storyline.nodes.core_nodes import load_media, split_shots, asr_node
    from open_storyline.nodes.core_nodes import speech_rough_cut, plan_timeline_pro
    from open_storyline.nodes.core_nodes import recommend_effects, render_video

    # The Pro timeline is the upstream implementation that consumes the
    # speech_rough_cut artifact. Its default prerequisites include optional
    # generation outputs, so this task-scoped metadata only requires the two
    # native artifacts actually used by this workflow.
    plan_timeline_pro.PlanTimelineProNode.meta.default_require_prior_kind = [
        "split_shots", "speech_rough_cut"
    ]

    # split_shots(mode="skip") is a pass-through; upstream __init__ eagerly
    # loads TransNet weights even in this mode. Defer model creation to the
    # explicit process() path, which still uses the unmodified native loader.
    def _skip_transnet_init(self, server_cfg):
        from open_storyline.utils.ffmpeg_utils import resolve_ffmpeg_executable
        from open_storyline.nodes.core_nodes.base_node import BaseNode
        BaseNode.__init__(self, server_cfg)
        self.transnetv2_model = None
        self.ffmpeg_executable = resolve_ffmpeg_executable()

    split_shots.SplitShotsNode.__init__ = _skip_transnet_init

    # OPENSTORYLINE-ASR-ADAPTER-01 overlay: inject the English paraformer
    # adapter into LocalASRNode. This replaces the stock funasr AutoModel
    # whose 1.3.1 wiring garbles this checkpoint's text (bpe.model decodes a
    # tokens.json id space) and drops word timestamps. The adapter keeps the
    # same models/weights (paraformer-en + fsmn-vad + ct-punc), decodes with
    # the checkpoint's own tokens.json table and computes word timestamps
    # from the model's CIF fire places. It raises on identity/vocab mismatch
    # instead of falling back.
    def _load_english_asr_model(self):
        if not hasattr(self, "asr_model"):
            # Validate the registered read-only cache before importing or
            # constructing any model. This keeps a missing mount from falling
            # through to ModelScope network lookup or a long opaque failure.
            from asr_adapter.cache_preflight import validate_asr_cache
            validate_asr_cache()
            from asr_adapter.paraformer_en import ParaformerEnAsr
            self.asr_model = ParaformerEnAsr()
        return self.asr_model

    asr_node.LocalASRNode._load_asr_model = _load_english_asr_model

    all_node_classes = [NODE_REGISTRY.get(name=node_name) for node_name in cfg.local_mcp_server.available_nodes]
    kind_to_node_id = {
        NodeClass.meta.node_kind: NodeClass.meta.node_id
        for NodeClass in all_node_classes
    }

    for NodeClass in all_node_classes:
        node_instance = NodeClass(cfg)
        input_schema = node_instance.input_schema

        tool_func, meta = create_tool_wrapper(node_instance, input_schema, cfg, kind_to_node_id)
        
        tool_name = NodeClass.meta.name
        tool_desc = NodeClass.meta.description
        
        # Register using server.tool decorator
        server.tool(
            name=tool_name,
            description=tool_desc,
            meta=asdict(meta)
        )(tool_func)

    # Register special tools (e.g., read_node_history)
    # local tool
    @server.tool(
        name="read_node_history",
        description="Retrieve the execution result of any node using its artifact_id"
    )
    async def mcp_read_history(
        mcp_ctx: Context[ServerSession, object],
        query_artifact_id: Annotated[str, Field(description="The artifact_id used to retrieve the corresponding JSON")]
    ) -> dict:
        node_summary = NodeSummary()
        request = mcp_ctx.request_context.request
        session_id = mcp_ctx.request_context.request.headers['X-Storyline-Session-Id']
        req_json_content = await request.json()
        params = req_json_content['params'].get('arguments', {'query_artifact_id': query_artifact_id})
        params['session_id'] = session_id
        params['node_summary'] = node_summary
    
        try:
            store = ArtifactStore(artifacts_dir=params.get('artifacts_dir', ".storyline/.server_cache"), session_id=session_id)
            meta, data = store.load_result(params['query_artifact_id'])
            summary = "History information retrieved successfully"
            isError = False
        except Exception as e:
            traceback_info = ''.join(traceback.format_exception(e))
            summary = f"History read execution failed: {params['query_artifact_id']}\n {traceback_info}",
            meta, data, isError = 'None', 'None', True

        return {
            'artifact_id': params.get('artifact_id', store.generate_artifact_id(req_json_content['params'].get('name', 'read_node_history'))),
            'tool_excute_result': {
                "history": {
                    "meta": meta,
                    "node_data": data,
                }
            },
            'summary': summary,
            'isError': isError,
        }

    @server.tool(
        name="write_skills",
        description="Save the generated Agent Skill (Markdown format) to the file system and return the absolute file path on success."
    )
    async def mcp_write_skills(
        mcp_ctx: Context[ServerSession, object],
        skill_name: Annotated[str, Field(description="Skill file name, e.g., 'fast_paced_vlog', without extension")],
        skill_dir: Annotated[str, Field(description="Skill storage directory, defaults to '.storyline/skills/'")] = '.storyline/skills/',
        skill_content: Annotated[str, Field(description="Skill content in Markdown format")] = '',
    ) -> dict:
        """
        Receives LLM-generated skill content and saves it as a local MD file.
        """
        node_summary = NodeSummary() 
        request = mcp_ctx.request_context.request
        session_id = request.headers.get('X-Storyline-Session-Id', 'unknown_session')
        req_json_content = await request.json()
        params = req_json_content.get('params', {}).get('arguments', {'skill_name': skill_name, 'skill_dir': skill_dir, 'skill_content': skill_content})
        params['session_id'] = session_id
        params['node_summary'] = node_summary
        
        res = await dump_skills(
            skill_name=skill_name,
            skill_dir=skill_dir,
            skill_content=skill_content,
        )
        node_summary.info_for_llm("[Write Skills] Done.")
        store = ArtifactStore(artifacts_dir=params.get('artifacts_dir', ".storyline/.server_cache"), session_id=session_id)

        return {
            'artifact_id': params.get('artifact_id', store.generate_artifact_id(req_json_content.get('params', {}).get('name', 'mcp_write_skills'))),
            'tool_excute_result': {
            },
            'summary': "",
            'isError': False,
        }
        
