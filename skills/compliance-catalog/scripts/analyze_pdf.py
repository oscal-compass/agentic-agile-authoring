#!/usr/bin/env python3
# Copyright OSCAL Compass Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
PDF structure analysis tool.

Analyzes PDF basic information and characteristics to provide
information needed for extraction script development.

Usage:
    python analyze_pdf.py <input.pdf> [--sample-pages N]

Output:
    - PDF basic info (page count, size, etc.)
    - Text layer presence
    - Sample page text extraction results
    - Recommended extraction method
"""

import argparse
import os
import sys

from pypdf import PdfReader


def analyze_pdf(pdf_path: str, sample_pages: int = 3) -> dict:
    """Analyze PDF and collect information."""
    reader = PdfReader(pdf_path)

    info = {
        "file_path": pdf_path,
        "file_size_mb": os.path.getsize(pdf_path) / (1024 * 1024),
        "page_count": len(reader.pages),
        "metadata": {},
        "pages_with_text": 0,
        "pages_without_text": 0,
        "sample_texts": [],
        "recommendations": [],
    }

    # Get metadata
    if reader.metadata:
        for key in ["/Title", "/Author", "/Subject", "/Creator", "/Producer"]:
            value = reader.metadata.get(key)
            if value:
                info["metadata"][key.replace("/", "")] = str(value)

    # Try text extraction for each page
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
            text = text.strip()

            if len(text) > 50:
                info["pages_with_text"] += 1
            else:
                info["pages_without_text"] += 1

            # Save sample page text
            if i < sample_pages:
                info["sample_texts"].append({
                    "page": i + 1,
                    "char_count": len(text),
                    "line_count": len(text.split("\n")) if text else 0,
                    "preview": text[:500] if text else "(No text extracted)",
                })
        except Exception as e:
            info["pages_without_text"] += 1
            if i < sample_pages:
                info["sample_texts"].append({
                    "page": i + 1,
                    "char_count": 0,
                    "line_count": 0,
                    "preview": f"(Error: {e})",
                })

    # Generate recommendations
    text_ratio = info["pages_with_text"] / info["page_count"] if info["page_count"] > 0 else 0

    if text_ratio > 0.9:
        info["recommendations"].append("Text PDF: Direct extraction with pypdf possible")
        info["recommended_method"] = "pypdf"
    elif text_ratio > 0.5:
        info["recommendations"].append("Mixed PDF: Determine text/OCR per page")
        info["recommended_method"] = "hybrid"
    else:
        info["recommendations"].append("Scanned PDF: OCR required")
        info["recommended_method"] = "ocr"

    if info["page_count"] > 50:
        info["recommendations"].append("Large PDF: Process per page to save memory")

    return info


def print_analysis(info: dict):
    """Display analysis results."""
    print("=" * 60)
    print("PDF Analysis Report")
    print("=" * 60)

    print(f"\nFile: {info['file_path']}")
    print(f"Size: {info['file_size_mb']:.2f} MB")
    print(f"Pages: {info['page_count']}")

    if info["metadata"]:
        print("\nMetadata:")
        for key, value in info["metadata"].items():
            print(f"  {key}: {value}")

    print(f"\nText Analysis:")
    print(f"  Pages with text: {info['pages_with_text']}")
    print(f"  Pages without text: {info['pages_without_text']}")
    print(f"  Text coverage: {info['pages_with_text'] / info['page_count'] * 100:.1f}%")

    print(f"\nRecommended Method: {info.get('recommended_method', 'unknown')}")
    for rec in info["recommendations"]:
        print(f"  - {rec}")

    print("\nSample Pages:")
    for sample in info["sample_texts"]:
        print(f"\n--- Page {sample['page']} ---")
        print(f"Characters: {sample['char_count']}, Lines: {sample['line_count']}")
        print(f"Preview:\n{sample['preview']}")
        if len(sample["preview"]) >= 500:
            print("... (truncated)")


def main():
    parser = argparse.ArgumentParser(description="Analyze PDF structure")
    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument("--sample-pages", type=int, default=3, help="Number of sample pages to show")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"Error: File not found: {args.pdf_path}")
        sys.exit(1)

    info = analyze_pdf(args.pdf_path, args.sample_pages)
    print_analysis(info)


if __name__ == "__main__":
    main()
