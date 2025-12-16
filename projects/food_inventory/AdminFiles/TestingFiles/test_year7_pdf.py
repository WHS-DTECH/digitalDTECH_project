#!/usr/bin/env python3
"""Test Year 7 PDF parsing to see what's on specific pages."""

import PyPDF2
import os

basedir = os.path.abspath(os.path.dirname(__file__))
pdf_path = os.path.join(basedir, 'RecipesPDF', "Year 7 Recipe Book.pdf")

if not os.path.exists(pdf_path):
    print(f"PDF not found at: {pdf_path}")
    exit(1)

print(f"Reading: {pdf_path}\n")

with open(pdf_path, 'rb') as f:
    pdf_reader = PyPDF2.PdfReader(f)
    print(f"Total pages: {len(pdf_reader.pages)}\n")
    
    # Check pages where recipes should be
    pages_to_check = [25, 26, 27, 32, 36, 48, 49, 50]
    
    for page_num in pages_to_check:
        if page_num <= len(pdf_reader.pages):
            print(f"\n{'='*80}")
            print(f"PAGE {page_num}")
            print('='*80)
            page = pdf_reader.pages[page_num - 1]  # 0-indexed
            text = page.extract_text()
            # Show first 1500 characters
            print(text[:1500])
            print("\n[... truncated ...]")
        else:
            print(f"\nPage {page_num} doesn't exist")
