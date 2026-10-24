"""Planning-time declaration of the configured video generator contract."""
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class VideoGenerationCapabilities:
    profile: str
    provider: str
    model: str
    video_reference_image_count: int
    supported_variation_types: tuple[str, ...]
    first_last_frame_control: bool

    def planning_guidance(self) -> str:
        if self.profile != "bailian-wan26-i2v-first-frame":
            raise RuntimeError(f"No planning guidance registered for {self.profile!r}")
        return (
            "Configured video capability: Bailian wan2.6-i2v-flash image-to-video "
            "accepts exactly one image, used as the first-frame reference; it does "
            "not accept an independent last-frame image or first/last pair. In the "
            "native ViMax schema, the supported variation_type for this route is "
            "'small' (the enum remains large/medium/small). Choose 'small' for "
            "every shot. Preserve the supplied principal action and describe "
            "natural subject/camera motion in motion_desc; small variation does "
            "not mean a static shot. Keep lf_desc and lf_vis_char_idxs because "
            "they are required native textual schema fields, and describe a "
            "coherent textual ending state. Those fields alone do not request a "
            "last-frame image: ViMax generates/passes that extra image only when "
            "variation_type is medium or large. Do not change the story, remove "
            "actions, or invent unsupported frame-control inputs."
        )


BAILIAN_WAN26_FIRST_FRAME_ONLY = VideoGenerationCapabilities(
    profile="bailian-wan26-i2v-first-frame",
    provider="bailian",
    model="wan2.6-i2v-flash",
    video_reference_image_count=1,
    supported_variation_types=("small",),
    first_last_frame_control=False,
)


def configured_video_generation_capabilities() -> VideoGenerationCapabilities | None:
    """Resolve only an explicitly frozen profile; unknown profiles fail closed."""
    profile = os.environ.get("VIMAX_VIDEO_CAPABILITY_PROFILE", "").strip()
    if not profile:
        return None
    if profile != BAILIAN_WAN26_FIRST_FRAME_ONLY.profile:
        raise RuntimeError(f"Unsupported VIMAX_VIDEO_CAPABILITY_PROFILE: {profile}")
    configured_model = os.environ.get("VIMAX_VIDEO_MODEL", "").strip()
    if configured_model and configured_model != BAILIAN_WAN26_FIRST_FRAME_ONLY.model:
        raise RuntimeError(
            "Video capability profile/model mismatch: "
            f"{profile} cannot describe configured model {configured_model!r}"
        )
    return BAILIAN_WAN26_FIRST_FRAME_ONLY
