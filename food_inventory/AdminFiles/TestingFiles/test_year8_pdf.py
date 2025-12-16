#!/usr/bin/env python3
"""Test Year 8 PDF parsing to find Beef Nachos."""

import PyPDF2
import os

basedir = os.path.abspath(os.path.dirname(__file__))
pdf_path = os.path.join(basedir, 'RecipesPDF', 'Year 8 Recipe Book.pdf')

if not os.path.exists(pdf_path):
    print(f"PDF not found at: {pdf_path}")
    exit(1)

print(f"Reading: {pdf_path}\n")

with open(pdf_path, 'rb') as f:
    pdf_reader = PyPDF2.PdfReader(f)
    print(f"Total pages: {len(pdf_reader.pages)}\n")
    
    # Search for "Beef Nachos" or "Nachos"
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text = page.extract_text()
        if 'nachos' in text.lower() or 'beef' in text.lower():
            print(f"\n{'='*80}")
            print(f"PAGE {page_num + 1} (contains 'nachos' or 'beef')")
            print('='*80)
            print(text[:2000])
            print("\n[... truncated ...]")
