#!/usr/bin/env python3
"""Clean up recipe database - remove duplicates and non-recipes."""

import sqlite3
import os
import json
import re

basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(basedir, 'recipes.db')

def remove_junk_recipes(conn):
    """Remove recipes that are clearly not recipes (worksheet questions, etc.)."""
    c = conn.cursor()
    c.execute('SELECT id, name, instructions FROM recipes')
    rows = c.fetchall()
    
    junk_patterns = [
        r'name \d+ different',
        r'working towards',
        r'tick the appropriate',
        r'correct all spellings',
        r'week \d+.*knowledge check',
        r'give \d+ example',
        r'what could happen',
        r'what does.*mean',
        r'how many',
        r'spellings',
        r'^skills$',
        r'^review$',
        r'unknown recipe',
        r'^\d+\.\d+\s+\d+$',  # Just numbers
        r'eatwell',
        r'hedonic scale',
        r'design your own',
        r'recipe writing sheet',
        r'●.*●.*●',  # Multiple bullet points (likely page headers)
        r'^year \d+.*food technology\s*$',  # Just year/food tech header
        r'^making activity\s*:?\s*$',  # Blank "Making Activity" with no name
        r'forfar bridies.*makes 2 bridies',  # Incomplete Forfar Bridies parse
        r'food preparation',  # "Food preparation skills"
        r'used in the',  # Partial sentences
        r'^you\.$',  # Just "you."
        r'salad:$',  # Ends with "salad:"
        r'cous\.$',  # Just "Cous."
    ]
    
    deleted = []
    for row in rows:
        recipe_id, name, instructions = row
        name_lower = name.lower() if name else ''
        inst_lower = instructions.lower() if instructions else ''
        
        # Skip recipes with very short names (likely junk)
        if name and len(name.strip()) < 3:
            print(f"Deleting recipe with too-short name: '{name}'")
            c.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
            deleted.append(name)
            continue
        
        # Check if name or instructions match junk patterns
        is_junk = False
        for pattern in junk_patterns:
            if re.search(pattern, name_lower) or re.search(pattern, inst_lower):
                is_junk = True
                break
        
        if is_junk:
            print(f"Deleting junk recipe: {name}")
            c.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
            deleted.append(name)
    
    conn.commit()
    return deleted


def remove_duplicate_recipes(conn):
    """Remove duplicate recipes based on normalized name."""
    c = conn.cursor()
    c.execute('SELECT id, name FROM recipes ORDER BY id')
    rows = c.fetchall()
    
    def normalize(s):
        if not s:
            return ''
        s = s.lower()
        # Remove extra spaces
        s = re.sub(r'\s+', ' ', s)
        s = s.strip()
        return s
    
    seen = {}
    deleted = []
    for row in rows:
        recipe_id, name = row
        norm_name = normalize(name)
        
        if norm_name in seen:
            print(f"Deleting duplicate: {name} (keeping id {seen[norm_name]})")
            c.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
            deleted.append(name)
        else:
            seen[norm_name] = recipe_id
    
    conn.commit()
    return deleted


def fix_recipe_names(conn):
    """Fix recipe names with spacing issues and remove prefixes."""
    c = conn.cursor()
    c.execute('SELECT id, name FROM recipes')
    rows = c.fetchall()
    
    fixed = []
    for row in rows:
        recipe_id, name = row
        original_name = name
        
        # Remove prefixes like "Making Activity 1:", "Year7 Food Technology 43"
        name = re.sub(r'^Making Activity\s+\d+:\s*', '', name, flags=re.I)
        name = re.sub(r'^Year\s*\d+\s+Food Technology\s+\d+\s*', '', name, flags=re.I)
        
        # Fix spacing issues like "Chee se" -> "Cheese", "Mushr oom" -> "Mushroom"
        # But don't join common connector words (and, or, with, etc.)
        # Split into words and check each pair
        words = name.split()
        fixed_words = []
        i = 0
        while i < len(words):
            if i < len(words) - 1:
                current = words[i]
                next_word = words[i + 1]
                # Skip if next word is a common connector
                connectors = ['and', 'or', 'with', '&', 'in', 'on', 'de', 'a', 'the']
                if next_word.lower() not in connectors and len(current) <= 6 and len(next_word) <= 4:
                    # Check if this looks like a broken word (both parts short)
                    if len(current) + len(next_word) <= 10:  # Reasonable word length
                        # Join them and skip next
                        fixed_words.append(current + next_word)
                        i += 2
                        continue
            fixed_words.append(words[i])
            i += 1
        name = ' '.join(fixed_words)
        
        # Clean up extra spaces
        name = re.sub(r'\s+', ' ', name).strip()
        
        if name != original_name:
            print(f"Fixing name: '{original_name}' -> '{name}'")
            # Check if this name already exists (duplicate after cleaning)
            c.execute('SELECT id FROM recipes WHERE name = ? AND id != ?', (name, recipe_id))
            existing = c.fetchone()
            if existing:
                print(f"  -> Would create duplicate, deleting this entry instead")
                c.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
            else:
                c.execute('UPDATE recipes SET name = ? WHERE id = ?', (name, recipe_id))
            fixed.append(original_name)
    
    conn.commit()
    return fixed


def main():
    print(f"Cleaning database: {DATABASE}")
    
    with sqlite3.connect(DATABASE) as conn:
        print("\n1. Removing junk recipes...")
        junk = remove_junk_recipes(conn)
        print(f"   Deleted {len(junk)} junk entries")
        
        print("\n2. Removing duplicates...")
        dupes = remove_duplicate_recipes(conn)
        print(f"   Deleted {len(dupes)} duplicates")
        
        print("\n3. Fixing recipe names...")
        fixed = fix_recipe_names(conn)
        print(f"   Fixed {len(fixed)} names")
        
        print("\n4. Final recipe count...")
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM recipes')
        count = c.fetchone()[0]
        print(f"   Total recipes: {count}")
        
        print("\n5. Recipe list:")
        c.execute('SELECT id, name FROM recipes ORDER BY name')
        for row in c.fetchall():
            print(f"   [{row[0]}] {row[1]}")
    
    print("\nDone!")


if __name__ == '__main__':
    main()
