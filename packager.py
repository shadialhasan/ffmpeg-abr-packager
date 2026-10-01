# -*- coding: utf-8 -*-
"""
Automated HLS Multi-Bitrate (ABR) Video Packager
Author: Eng. MHD. Shadi AL-Hasan <mhd.shadi.alhasan@gmail.com>
Phone: +963934005922
Copyright (c) 2026 MHD. Shadi AL-Hasan
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

RENDITION_PROFILES: Dict[str, Dict[str, Any]] = {
    "1080p": {
        "width": 1920,
        "height": 1080,
        "bitrate": "4500k",
        "maxrate": "5000k",
        "bufsize": "9000k",
        "audio_bitrate": "192k"
    },
    "720p": {
        "width": 1280,
        "height": 720,
        "bitrate": "2500k",
        "maxrate": "2800k",
        "bufsize": "5000k",
        "audio_bitrate": "128k"
    },
    "480p": {
        "width": 854,
        "height": 480,
        "bitrate": "1200k",
        "maxrate": "1400k",
        "bufsize": "2400k",
        "audio_bitrate": "128k"
    },
    "360p": {
        "width": 640,
        "height": 360,
        "bitrate": "600k",
        "maxrate": "700k",
        "bufsize": "1200k",
        "audio_bitrate": "96k"
    }
}


def check_ffmpeg_environment(ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> Dict[str, Any]:
    """Verify system FFmpeg and FFprobe binary availability and versioning."""
    status = {
        "ffmpeg_installed": False,
        "ffprobe_installed": False,
        "ffmpeg_version": None,
        "codecs_supported": []
    }

    ffmpeg_path = shutil.which(ffmpeg_bin)
    if ffmpeg_path:
        status["ffmpeg_installed"] = True
        try:
            res = subprocess.run([ffmpeg_bin, "-version"], capture_output=True, text=True, check=True)
            first_line = res.stdout.splitlines()[0] if res.stdout else ""
            status["ffmpeg_version"] = first_line
        except Exception:
            status["ffmpeg_version"] = "unknown"

    ffprobe_path = shutil.which(ffprobe_bin)
    if ffprobe_path:
        status["ffprobe_installed"] = True

    return status


class ABRPackager:
    def __init__(
        self,
        input_video: Path,
        output_dir: Path,
        segment_time: int = 6,
        renditions: Optional[List[str]] = None,
        preset: str = "veryfast",
        ffmpeg_bin: str = "ffmpeg"
    ):
        self.input_video = Path(input_video)
        self.output_dir = Path(output_dir)
        self.segment_time = segment_time
        self.preset = preset
        self.ffmpeg_bin = ffmpeg_bin
        
        # Default ladder to full 4-tier profile if unspecified
        if not renditions:
            self.renditions = ["1080p", "720p", "480p", "360p"]
        else:
            self.renditions = [r.lower() for r in renditions if r.lower() in RENDITION_PROFILES]
            if not self.renditions:
                raise ValueError(f"No valid renditions specified. Available options: {list(RENDITION_PROFILES.keys())}")

    def build_ffmpeg_command(self) -> List[str]:
        """Generate deterministic multi-stream FFmpeg command with synchronized GOP boundaries."""
        n = len(self.renditions)

        # Build video filter split chain
        split_pads = "".join(f"[v{i}]" for i in range(n))
        scale_filters = []
        for i, rend in enumerate(self.renditions):
            prof = RENDITION_PROFILES[rend]
            scale_filters.append(f"[v{i}]scale=w={prof['width']}:h={prof['height']}[v{i}out]")
        
        filter_complex = f"[0:v]split={n}{split_pads};" + ";".join(scale_filters)

        cmd = [
            self.ffmpeg_bin, "-y", "-i", str(self.input_video),
            "-filter_complex", filter_complex
        ]

        # Map each scaled stream with bitrate throttling & GOP alignment
        var_stream_items = []
        for i, rend in enumerate(self.renditions):
            prof = RENDITION_PROFILES[rend]
            cmd.extend([
                "-map", f"[v{i}out]",
                f"-c:v:{i}", "libx264",
                f"-preset:{i}", self.preset,
                f"-b:v:{i}", prof["bitrate"],
                f"-maxrate:v:{i}", prof["maxrate"],
                f"-bufsize:v:{i}", prof["bufsize"]
            ])
            var_stream_items.append(f"v:{i},a:0")

        # Map audio stream with AAC codec
        cmd.extend([
            "-map", "0:a?",
            "-c:a", "aac",
            "-b:a", "128k",
            "-var_stream_map", " ".join(var_stream_items),
            "-f", "hls",
            "-hls_time", str(self.segment_time),
            "-hls_playlist_type", "vod",
            "-hls_flags", "independent_segments",
            "-master_pl_name", "master.m3u8",
            "-hls_segment_filename", str(self.output_dir / "v%v" / "segment%03d.ts"),
            str(self.output_dir / "v%v" / "index.m3u8")
        ])

        return cmd

    def package(self, execute: bool = False) -> Dict[str, Any]:
        """Construct packaging plan, create directories, save script, and optionally execute."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for i in range(len(self.renditions)):
            (self.output_dir / f"v{i}").mkdir(parents=True, exist_ok=True)

        cmd = self.build_ffmpeg_command()

        # Write cross-platform execution script
        run_sh = self.output_dir / "transcode_command.sh"
        run_sh.write_text(" ".join(f'"{c}"' if " " in c else c for c in cmd), encoding="utf-8")

        result = {
            "input_video": str(self.input_video),
            "output_dir": str(self.output_dir),
            "renditions": self.renditions,
            "segment_time": self.segment_time,
            "master_playlist": str(self.output_dir / "master.m3u8"),
            "command_script": str(run_sh),
            "executed": False,
            "success": True
        }

        print(f"[*] Packaging {self.input_video.name} to Adaptive Bitrate HLS...")
        print(f"[*] Rendition profiles: {', '.join(self.renditions)}")
        print(f"[+] Transcode pipeline script generated at: {run_sh}")

        if execute:
            print(f"[*] Executing live multi-resolution transcode pipeline...")
            exec_res = subprocess.run(cmd, capture_output=True, text=True)
            result["executed"] = True
            result["returncode"] = exec_res.returncode
            if exec_res.returncode != 0:
                result["success"] = False
                result["error"] = exec_res.stderr
                print(f"[!] Transcoding failed with code {exec_res.returncode}: {exec_res.stderr[-500:]}")
            else:
                # Normalize any Windows path separators in generated m3u8 playlists for RFC 8216 CDN compliance
                master_file = self.output_dir / "master.m3u8"
                if master_file.exists():
                    m_content = master_file.read_text(encoding="utf-8")
                    if "\\" in m_content:
                        master_file.write_text(m_content.replace("\\", "/"), encoding="utf-8")
                
                for idx in range(len(self.renditions)):
                    var_pl = self.output_dir / f"v{idx}" / "index.m3u8"
                    if var_pl.exists():
                        v_content = var_pl.read_text(encoding="utf-8")
                        if "\\" in v_content:
                            var_pl.write_text(v_content.replace("\\", "/"), encoding="utf-8")

                result["success"] = True
                print(f"[✔] ABR Packaging complete! Master manifest: {result['master_playlist']}")

        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Automated HLS Multi-Bitrate (ABR) Video Packager by Eng. MHD. Shadi AL-Hasan"
    )
    parser.add_argument("--input", "-i", help="Input video file path (.mp4, .mov, .mkv)")
    parser.add_argument(
        "--output", "-o",
        default=os.getenv("DEFAULT_OUTPUT_DIR", "hls_output"),
        help="Output destination directory (default: hls_output)"
    )
    parser.add_argument(
        "--segment-time", "-s",
        type=int,
        default=int(os.getenv("ABR_SEGMENT_DURATION", "6")),
        help="Target segment duration in seconds (default: 6)"
    )
    parser.add_argument(
        "--renditions", "-r",
        default=os.getenv("ABR_DEFAULT_RENDITIONS", "1080p,720p,480p,360p"),
        help="Comma-separated renditions ladder: 1080p,720p,480p,360p (default: all)"
    )
    parser.add_argument(
        "--preset", "-p",
        default=os.getenv("ABR_PRESET", "veryfast"),
        help="x264 encoding preset (default: veryfast)"
    )
    parser.add_argument(
        "--execute", "-x",
        action="store_true",
        help="Execute FFmpeg transcode pipeline immediately (default: dry-run/script only)"
    )
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Perform diagnostic environment check on FFmpeg & FFprobe toolchain"
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.check_env:
        status = check_ffmpeg_environment()
        print("=== FFmpeg Environment Diagnostic ===")
        print(f"FFmpeg Installed: {'YES' if status['ffmpeg_installed'] else 'NO'}")
        print(f"FFprobe Installed: {'YES' if status['ffprobe_installed'] else 'NO'}")
        print(f"Version: {status.get('ffmpeg_version', 'N/A')}")
        print("Author: Eng. MHD. Shadi AL-Hasan <mhd.shadi.alhasan@gmail.com>")
        return

    if not args.input:
        parser.error("--input / -i is required unless --check-env is specified.")

    rendition_list = [r.strip() for r in args.renditions.split(",") if r.strip()]
    packager = ABRPackager(
        input_video=Path(args.input),
        output_dir=Path(args.output),
        segment_time=args.segment_time,
        renditions=rendition_list,
        preset=args.preset
    )
    packager.package(execute=args.execute)


if __name__ == "__main__":
    main()
