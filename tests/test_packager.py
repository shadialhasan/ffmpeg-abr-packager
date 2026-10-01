# -*- coding: utf-8 -*-
"""
Automated Transcoding & Unit Tests for FFmpeg ABR Packager
Author: Eng. MHD. Shadi AL-Hasan <mhd.shadi.alhasan@gmail.com>
"""

import shutil
import subprocess
from pathlib import Path
import pytest

from packager import (
    ABRPackager,
    check_ffmpeg_environment,
    build_parser,
    RENDITION_PROFILES
)


class TestABRPackager:
    def test_environment_check(self):
        status = check_ffmpeg_environment()
        assert isinstance(status, dict)
        assert "ffmpeg_installed" in status
        assert "ffprobe_installed" in status
        assert "ffmpeg_version" in status

    def test_packager_initialization_defaults(self, tmp_path):
        dummy_in = tmp_path / "video.mp4"
        out_dir = tmp_path / "hls_out"
        packager = ABRPackager(input_video=dummy_in, output_dir=out_dir)

        assert packager.renditions == ["1080p", "720p", "480p", "360p"]
        assert packager.segment_time == 6
        assert packager.preset == "veryfast"

    def test_packager_invalid_renditions(self, tmp_path):
        dummy_in = tmp_path / "video.mp4"
        out_dir = tmp_path / "hls_out"
        with pytest.raises(ValueError, match="No valid renditions specified"):
            ABRPackager(input_video=dummy_in, output_dir=out_dir, renditions=["4k_ultra_hdr", "8k"])

    def test_build_ffmpeg_command_full_ladder(self, tmp_path):
        dummy_in = tmp_path / "input.mp4"
        out_dir = tmp_path / "hls_out"
        packager = ABRPackager(input_video=dummy_in, output_dir=out_dir)
        cmd = packager.build_ffmpeg_command()

        cmd_str = " ".join(cmd)
        assert "ffmpeg" in cmd[0]
        assert "-filter_complex" in cmd
        assert "[0:v]split=4[v0][v1][v2][v3]" in cmd_str
        assert "scale=w=1920:h=1080[v0out]" in cmd_str
        assert "scale=w=1280:h=720[v1out]" in cmd_str
        assert "scale=w=854:h=480[v2out]" in cmd_str
        assert "scale=w=640:h=360[v3out]" in cmd_str
        assert "-var_stream_map" in cmd
        assert "v:0,a:0 v:1,a:0 v:2,a:0 v:3,a:0" in cmd_str
        assert "master.m3u8" in cmd_str

    def test_build_ffmpeg_command_custom_ladder(self, tmp_path):
        dummy_in = tmp_path / "source.mkv"
        out_dir = tmp_path / "custom_out"
        packager = ABRPackager(input_video=dummy_in, output_dir=out_dir, renditions=["720p", "360p"], segment_time=4)
        cmd = packager.build_ffmpeg_command()

        cmd_str = " ".join(cmd)
        assert "[0:v]split=2[v0][v1]" in cmd_str
        assert "scale=w=1280:h=720[v0out]" in cmd_str
        assert "scale=w=640:h=360[v1out]" in cmd_str
        assert "v:0,a:0 v:1,a:0" in cmd_str
        assert "-hls_time 4" in cmd_str

    def test_package_dry_run_script_generation(self, tmp_path):
        dummy_in = tmp_path / "trailer.mp4"
        out_dir = tmp_path / "hls_dist"
        packager = ABRPackager(input_video=dummy_in, output_dir=out_dir, renditions=["720p"])
        res = packager.package(execute=False)

        assert res["executed"] is False
        assert res["success"] is True
        assert (out_dir / "v0").is_dir()
        script_file = out_dir / "transcode_command.sh"
        assert script_file.is_file()
        content = script_file.read_text(encoding="utf-8")
        assert "ffmpeg" in content
        assert "master.m3u8" in content

    def test_cli_parser_options(self):
        parser = build_parser()
        args = parser.parse_args(["--input", "raw.mp4", "--output", "out_cdn", "--renditions", "1080p,720p", "--execute"])
        assert args.input == "raw.mp4"
        assert args.output == "out_cdn"
        assert args.renditions == "1080p,720p"
        assert args.execute is True

    @pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg system binary not installed")
    def test_live_transcode_verification(self, tmp_path):
        """End-to-end transcode verification using a generated synthetic media sample."""
        sample_input = tmp_path / "synthetic_test.mp4"
        gen_cmd = [
            "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=1:size=640x360:rate=10",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-c:v", "libx264", "-c:a", "aac", "-t", "1", "-y", str(sample_input)
        ]
        gen_res = subprocess.run(gen_cmd, capture_output=True, text=True)
        assert gen_res.returncode == 0, f"Synthetic generator failed: {gen_res.stderr}"
        assert sample_input.is_file()

        hls_output = tmp_path / "hls_ladder"
        packager = ABRPackager(
            input_video=sample_input,
            output_dir=hls_output,
            segment_time=1,
            renditions=["360p"],
            preset="ultrafast"
        )

        result = packager.package(execute=True)
        assert result["executed"] is True
        assert result["success"] is True, f"ABR transcoding failed: {result.get('error')}"

        # 1. Verify master manifest
        master_m3u8 = hls_output / "master.m3u8"
        assert master_m3u8.is_file(), "master.m3u8 was not generated"
        master_content = master_m3u8.read_text(encoding="utf-8")
        assert "#EXTM3U" in master_content
        assert "v0/index.m3u8" in master_content

        # 2. Verify variant playlist
        variant_m3u8 = hls_output / "v0" / "index.m3u8"
        assert variant_m3u8.is_file(), "variant index.m3u8 was not generated"
        variant_content = variant_m3u8.read_text(encoding="utf-8")
        assert "#EXT-X-TARGETDURATION" in variant_content
        assert "segment000.ts" in variant_content

        # 3. Verify media segment file
        segment_0 = hls_output / "v0" / "segment000.ts"
        assert segment_0.is_file(), "segment000.ts was not generated"
        assert segment_0.stat().st_size > 0, "segment000.ts is empty"
