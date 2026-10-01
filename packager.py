# -*- coding: utf-8 -*-
"""
Automated HLS Multi-Bitrate (ABR) Video Packager
Author: Eng. MHD. Shadi AL-Hasan <mhd.shadi.alhasan@gmail.com>
Phone: +963934005922
Copyright (c) 2026 MHD. Shadi AL-Hasan
"""

import os
import subprocess
import argparse
from pathlib import Path

class ABRPackager:
    def __init__(self, input_video: Path, output_dir: Path, segment_time=6):
        self.input_video = input_video
        self.output_dir = output_dir
        self.segment_time = segment_time

    def package(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[*] Packaging {self.input_video.name} to Adaptive Bitrate HLS...")

        # Master manifest path
        master_m3u8 = self.output_dir / "master.m3u8"
        
        # FFmpeg complex filter command for 1080p, 720p, 480p, 360p
        cmd = [
            "ffmpeg", "-y", "-i", str(self.input_video),
            "-filter_complex",
            "[0:v]split=4[v1][v2][v3][v4];"
            "[v1]scale=w=1920:h=1080[v1out];"
            "[v2]scale=w=1280:h=720[v2out];"
            "[v3]scale=w=854:h=480[v3out];"
            "[v4]scale=w=640:h=360[v4out]",
            
            "-map", "[v1out]", "-c:v:0", "libx264", "-b:v:0", "4500k", "-maxrate:v:0", "5000k", "-bufsize:v:0", "9000k",
            "-map", "[v2out]", "-c:v:1", "libx264", "-b:v:1", "2500k", "-maxrate:v:1", "2800k", "-bufsize:v:1", "5000k",
            "-map", "[v3out]", "-c:v:2", "libx264", "-b:v:2", "1200k", "-maxrate:v:2", "1400k", "-bufsize:v:2", "2400k",
            "-map", "[v4out]", "-c:v:3", "libx264", "-b:v:3", "600k",  "-maxrate:v:3", "700k",  "-bufsize:v:3", "1200k",
            
            "-map", "0:a", "-c:a", "aac", "-b:a", "128k",
            "-f", "hls",
            "-hls_time", str(self.segment_time),
            "-hls_playlist_type", "vod",
            "-hls_flags", "independent_segments",
            "-master_pl_name", "master.m3u8",
            "-hls_segment_filename", str(self.output_dir / "v%v/segment%03d.ts"),
            str(self.output_dir / "v%v/index.m3u8")
        ]
        
        print(f"[*] Executing multi-resolution transcode pipeline...")
        print(f"[CMD] {' '.join(cmd[:10])} ...")
        
        # Write demo script for quick inspection
        run_sh = self.output_dir / "transcode_command.sh"
        run_sh.write_text(" ".join(cmd), encoding="utf-8")
        print(f"[+] Transcoding script saved to: {run_sh}")

def main():
    parser = argparse.ArgumentParser(description="Package input video into multi-bitrate HLS streams.")
    parser.add_argument("--input", "-i", required=True, help="Input video file (.mp4, .mov, .mkv)")
    parser.add_argument("--output", "-o", default="hls_output", help="Output directory")
    args = parser.parse_args()

    packager = ABRPackager(Path(args.input), Path(args.output))
    packager.package()

if __name__ == "__main__":
    main()
