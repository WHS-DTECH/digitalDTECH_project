import PyPDF2
from recipe_parser import parse_recipes_from_text

# Test with the Year 8 PDF
pdf_path = 'RecipesPDF/St Mary\'s eatwell-guide-booklet-yr8 2023.pdf'

with open(pdf_path, 'rb') as pdf_file:
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    print(f"Total pages: {len(pdf_reader.pages)}")
    
    all_recipes = []
    for page_num, page in enumerate(pdf_reader.pages):
        text = page.extract_text()
        recipes = parse_recipes_from_text(text)
        if recipes:
            print(f"Page {page_num + 1}: Found {len(recipes)} recipe(s)")
            for r in recipes:
                print(f"  - {r['name']}")
            all_recipes.extend(recipes)
    
    print(f"\nTotal recipes found: {len(all_recipes)}")
