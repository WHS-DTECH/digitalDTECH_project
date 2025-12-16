"""Recipe parser for extracting recipes from PDF documents."""

import re


def parse_recipes_from_text(text):
    """Parse recipes from PDF text that contain Ingredients, Equipment, and Method sections.

    This version is tolerant of trailing spaces, wrapped lines (equipment lists
    that continue on the next line), and repeated section headers.
    """
    recipes = []
    lines = text.split('\n')

    recipe_data = None
    current_section = None

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        line_lower = line.lower()

        # Recipe title marker: "Making Activity : <name>"
        if 'making activity' in line_lower and ':' in raw:
            # save previous recipe if complete
            if recipe_data and recipe_data.get('ingredients') and recipe_data.get('equipment') and recipe_data.get('method'):
                recipes.append(format_recipe(recipe_data))

            # start new recipe
            recipe_name = raw.replace('Making Activity :', '').replace('Making Activity:', '').strip()
            recipe_data = {'name': recipe_name, 'ingredients': [], 'equipment': [], 'method': []}
            current_section = None
            i += 1
            continue

        # If no recipe started yet, try to infer one from an ingredient line
        if not recipe_data:
            # simple ingredient detection: starts with a number or contains common units
            ll = line.lower()
            def looks_like_ingredient(s):
                if not s:
                    return False
                # Skip single page numbers (1-3 digits alone)
                if s.strip().isdigit() and len(s.strip()) <= 3:
                    return False
                if s[0].isdigit():
                    return True
                for token in ['g ', 'ml', 'cup', 'tsp', 'tbsp', 'tablespoon', 'teaspoon', 'slice', 'large', 'small', 'packet', 'can']:
                    if token in s:
                        return True
                if s.startswith('•'):
                    return True
                return False

            if looks_like_ingredient(ll):
                # Look back for a plausible title within previous 15 lines
                # Collect all non-junk lines, then pick the best title candidate
                candidates = []
                for j in range(1, 15):
                    idx = i - j
                    if idx < 0:
                        break
                    cand = lines[idx].strip()
                    low = cand.lower()
                    
                    if not cand:
                        continue
                    
                    # Skip obvious junk
                    if low.isdigit():
                        continue
                    if any(k in low for k in ['learning objective', 'page ', 'food technology', 'assessment', 'evaluation', 'scenario:', 'brief:', 'attributes:']):
                        continue
                    
                    # Check if it's an ingredient line (stop looking back)
                    def _looks_like_ingredient(s):
                        if not s:
                            return False
                        if s[0].isdigit():
                            return True
                        for token in ['g ', 'ml', 'cup', 'tsp', 'tbsp', 'tablespoon', 'teaspoon', 'slice']:
                            if token in s:
                                return True
                        if s.startswith('•'):
                            return True
                        return False
                    
                    if _looks_like_ingredient(low):
                        break
                    
                    # Add to candidates
                    candidates.append(cand)
                
                # Find best title from candidates
                title = None
                for cand in candidates:
                    low = cand.lower()
                    # Skip section headers like "Week 9 :" 
                    if 'week ' in low and ':' in cand:
                        continue
                    # Skip continuation lines that aren't real titles
                    if cand.startswith(('group of', ')', 'work in pairs')):
                        continue
                    # Prefer lines that look like recipe names (not too long, no excessive punctuation)
                    if 3 < len(cand) < 100 and cand.count('.') < 3:
                        # This looks like a good title
                        title = cand
                        break
                
                if title:
                    # Clean up title - remove common prefixes/suffixes
                    title = re.sub(r'\(per.*$', '', title).strip()  # Remove "(per..." to end
                    title = re.sub(r'\(makes \d+ .*?\)', '', title, flags=re.I).strip()
                    title = re.sub(r'–\s*work in pairs', '', title, flags=re.I).strip()
                else:
                    title = 'Unknown Recipe'
                    
                recipe_data = {'name': title, 'ingredients': [], 'equipment': [], 'method': []}
                current_section = 'ingredients'
                # fall through to collect this ingredient line
            else:
                i += 1
                continue

        # Section headers may have trailing spaces or internal splits (e.g. "Ingredi ents")
        alpha = ''.join(ch for ch in line_lower if ch.isalpha())
        if alpha.startswith('ingredients') or line_lower.startswith('ingredients'):
            # If we have no recipe started yet but hit ingredients, look back for a title
            if not recipe_data or not recipe_data.get('name'):
                title = None
                for j in range(1, 10):
                    idx = i - j
                    if idx < 0:
                        break
                    cand = lines[idx].strip()
                    if cand and len(cand) > 3 and len(cand) < 100:
                        low = cand.lower()
                        # Skip headers and junk
                        if not any(skip in low for skip in ['learning objective', 'keywords', 'equipment', 'method', 'week ', 'page ', 'food technology', 'by the end']):
                            title = cand
                            break
                if title and not recipe_data:
                    recipe_data = {'name': title, 'ingredients': [], 'equipment': [], 'method': []}
            current_section = 'ingredients'
            i += 1
            continue
        if alpha.startswith('equipment') or line_lower.startswith('equipment'):
            # If we have no recipe started yet but hit equipment, look back for a title
            if not recipe_data or not recipe_data.get('name'):
                title = None
                for j in range(1, 10):
                    idx = i - j
                    if idx < 0:
                        break
                    cand = lines[idx].strip()
                    if cand and len(cand) > 3 and len(cand) < 100:
                        low = cand.lower()
                        # Skip headers and junk
                        if not any(skip in low for skip in ['learning objective', 'keywords', 'ingredients', 'method', 'week ', 'page ', 'food technology', 'by the end']):
                            title = cand
                            break
                if title and not recipe_data:
                    recipe_data = {'name': title, 'ingredients': [], 'equipment': [], 'method': []}
            current_section = 'equipment'
            i += 1
            continue
        if alpha.startswith('method') or line_lower.startswith('method'):
            current_section = 'method'
            i += 1
            continue

        # End markers
        if any(marker in line_lower for marker in ['top tips', 'skills', 'evaluation', 'assessment']):
            # accept recipes that have ingredients and method (equipment optional)
            if recipe_data.get('ingredients') and recipe_data.get('method'):
                recipes.append(format_recipe(recipe_data))
            recipe_data = None
            current_section = None
            i += 1
            continue

        # Collect content: join wrapped equipment lines if necessary
        if current_section:
            if not line:
                i += 1
                continue
            # Remove bullet markers
            if line.startswith('•'):
                line = line[1:].strip()

            # If equipment line contains commas and may be wrapped, try to merge
            if current_section == 'equipment':
                # If previous equipment entry looks like a continuation (no comma and ends with a word), append
                if recipe_data['equipment'] and not recipe_data['equipment'][-1].endswith(',') and not recipe_data['equipment'][-1].endswith('.') and not recipe_data['equipment'][-1].endswith(':'):
                    # append as continuation
                    recipe_data['equipment'][-1] = recipe_data['equipment'][-1] + ' ' + line
                else:
                    recipe_data['equipment'].append(line)
            else:
                recipe_data[current_section].append(line)

        i += 1

    # final recipe
    if recipe_data and recipe_data.get('ingredients') and recipe_data.get('method'):
        recipes.append(format_recipe(recipe_data))

    return recipes


def format_recipe(recipe_data):
    """Format parsed recipe data into structured format for database."""
    # Parse ingredients into structured format
    ingredients = []
    for ing_line in recipe_data.get('ingredients', []):
        ing_line = ing_line.strip()
        if ing_line:
            ingredients.append(parse_ingredient_line(ing_line))

    # Parse equipment into list (split by comma or individual entries)
    equipment_text = ' '.join(recipe_data.get('equipment', []))
    equipment = [e.strip() for e in equipment_text.split(',') if e.strip()]
    if not equipment:
        # Try splitting by space if no commas
        equipment = [e.strip() for e in equipment_text.split() if e.strip()]

    # Parse method - keep as multi-line text
    method_text = '\n'.join(recipe_data.get('method', []))

    return {
        'name': recipe_data.get('name', 'Unknown Recipe').strip(),
        'ingredients': ingredients,
        'equipment': equipment,
        'method': method_text,
        'serving_size': None
    }


def parse_ingredient_line(line):
    """Parse a single ingredient line into quantity, unit, and ingredient name."""
    line = line.strip()

    if not line:
        return {"quantity": "", "unit": "", "ingredient": ""}

    parts = line.split(maxsplit=3)

    # Try to extract numeric quantity from first part
    quantity = ""
    unit = ""
    ingredient = ""

    if not parts:
        return {"quantity": "", "unit": "", "ingredient": line}

    # Check if first part looks like a number
    first_part = parts[0]
    quantity_val = None

    try:
        # Try simple float
        quantity_val = float(first_part.replace('g', '').replace('ml', ''))
        quantity = str(quantity_val)
    except ValueError:
        # Check for fraction or "x" patterns like "2 x 5ml"
        if 'x' in first_part.lower():
            # Might be something like "2x5ml" - keep as is
            ingredient = line
            return {"quantity": "", "unit": "", "ingredient": ingredient}
        else:
            # Couldn't parse as number, treat whole line as ingredient
            return {"quantity": "", "unit": "", "ingredient": line}

    # We have a quantity, now extract unit and ingredient
    if len(parts) >= 2:
        unit = parts[1]
        ingredient = ' '.join(parts[2:]) if len(parts) > 2 else ''

    # Clean up unit (remove 'x' if present)
    if unit:
        unit = unit.replace('x', '').strip()

    return {
        "quantity": quantity,
        "unit": unit,
        "ingredient": ingredient if ingredient else line
    }
