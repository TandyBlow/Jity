"""
Render Mermaid diagrams to PNG via mermaid.ink API.
No dependencies beyond Python stdlib.
"""
import zlib
import base64
import urllib.request
import os
import json

DIAGRAMS_DIR = os.path.join(os.path.dirname(__file__), "diagrams")
OUTPUT_DIR = DIAGRAMS_DIR  # Output PNGs to same directory

DIAGRAMS = {
    "fig3_1_system_architecture.png": "fig3_1_system_architecture.mmd",
    "fig3_2_memory_architecture.png": "fig3_2_memory_architecture.mmd",
    "fig3_3_agent_pipeline.png": "fig3_3_agent_pipeline.mmd",
    "fig3_4_campaign_fsm.png": "fig3_4_campaign_fsm.mmd",
    "fig3_5_turn_dataflow.png": "fig3_5_turn_dataflow.mmd",
}


def encode_mermaid(mermaid_code: str) -> str:
    """Encode Mermaid code for mermaid.ink API.

    Format: pako_deflate → base64url
    Mermaid.ink URL: https://mermaid.ink/img/pako:<encoded>
    """
    # pako is just zlib (deflate) with a custom header
    # pako.deflate uses raw deflate (no zlib header)
    compressed = zlib.compress(mermaid_code.encode("utf-8"), level=9)[2:-4]
    # base64url encode (use - and _ instead of + and /, no padding)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return encoded


def render_diagram(mermaid_path: str, output_path: str, width: int = 1600) -> bool:
    """Render a Mermaid .mmd file to PNG via mermaid.ink."""
    with open(mermaid_path, "r", encoding="utf-8") as f:
        mermaid_code = f.read()

    encoded = encode_mermaid(mermaid_code)
    # Use /img/ endpoint for PNG
    url = f"https://mermaid.ink/img/pako:{encoded}?type=png&width={width}"

    print(f"  Rendering: {os.path.basename(mermaid_path)}")
    print(f"    Mermaid code: {len(mermaid_code)} chars")
    print(f"    Encoded: {len(encoded)} chars")
    print(f"    URL length: {len(url)}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Jity-Thesis/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            img_data = resp.read()

        with open(output_path, "wb") as f:
            f.write(img_data)

        size_kb = len(img_data) / 1024
        print(f"    OK: {size_kb:.1f} KB → {os.path.basename(output_path)}")
        return True

    except Exception as e:
        print(f"    ERROR: {e}")
        # Try alternative: use /svg/ endpoint then note for manual conversion
        try:
            svg_url = f"https://mermaid.ink/svg/pako:{encoded}"
            req2 = urllib.request.Request(svg_url, headers={"User-Agent": "Jity-Thesis/1.0"})
            with urllib.request.urlopen(req2, timeout=30) as resp2:
                svg_data = resp2.read()
            svg_path = output_path.replace(".png", ".svg")
            with open(svg_path, "wb") as f:
                f.write(svg_data)
            print(f"    Fallback SVG: {len(svg_data)/1024:.1f} KB → {os.path.basename(svg_path)}")
            return True
        except Exception as e2:
            print(f"    SVG fallback also failed: {e2}")
            return False


def main():
    print("=" * 60)
    print("Rendering Mermaid Diagrams for FYP Thesis")
    print("=" * 60)

    success = 0
    failed = 0

    for png_name, mmd_name in DIAGRAMS.items():
        mmd_path = os.path.join(DIAGRAMS_DIR, mmd_name)
        png_path = os.path.join(OUTPUT_DIR, png_name)

        if not os.path.exists(mmd_path):
            print(f"\n  SKIP: {mmd_name} not found")
            failed += 1
            continue

        print()
        if render_diagram(mmd_path, png_path):
            success += 1
        else:
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Done: {success} OK, {failed} failed")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
