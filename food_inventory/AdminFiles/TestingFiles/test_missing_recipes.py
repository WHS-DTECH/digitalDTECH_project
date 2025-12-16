#!/usr/bin/env python3
"""Test if parser can extract Beef Nachos and Forfar Bridies."""

import sys
sys.path.insert(0, '/home/WHSDTECH/FOOORMINVENTORY')

from recipe_parser import parse_recipes_from_text
import PyPDF2

# Test with Year 8 PDF - Beef Nachos on page 45
print("Testing Year 8 PDF for Beef Nachos...")
with open('/home/WHSDTECH/FOOORMINVENTORY/RecipesPDF/Year 8 Recipe Book.pdf', 'rb') as f:
    pdf = PyPDF2.PdfReader(f)
    page_45 = pdf.pages[44]  # 0-indexed
    text = page_45.extract_text()
    
    print("\n=== PAGE 45 TEXT ===")
    print(text[:1000])
    
    print("\n=== PARSING RESULTS ===")
    recipes = parse_recipes_from_text(text)
    print(f"Found {len(recipes)} recipe(s):")
    for r in recipes:
        print(f"  - Name: {r['name']}")
        print(f"    Ingredients: {len(r.get('ingredients', []))} items")
        print(f"    Method lines: {len(r.get('method', '').split(chr(10)) if isinstance(r.get('method'), str) else r.get('method', []))}")
        if r.get('ingredients'):
            print(f"    First ingredient: {r['ingredients'][0]}")

print("\n" + "="*80)
print("\nTesting Year 7 PDF for Forfar Bridies...")
with open('/home/WHSDTECH/FOOORMINVENTORY/RecipesPDF/Year 7 Recipe Book.pdf', 'rb') as f:
    pdf = PyPDF2.PdfReader(f)
    # Try pages 49 and 50 together since recipe might span pages
    text = pdf.pages[48].extract_text() + "\n" + pdf.pages[49].extract_text()
    
    print("\n=== PAGES 49-50 TEXT (first 1500 chars) ===")
    print(text[:1500])
    
    print("\n=== PARSING RESULTS ===")
    recipes = parse_recipes_from_text(text)
    print(f"Found {len(recipes)} recipe(s):")
    for r in recipes:
        print(f"  - {r['name']}")
