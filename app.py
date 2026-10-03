import os
import json
import time
import requests

# Direct Windows paths for your F: drive
BASE_DIR = r"F:\BOOK_OCR"
COVERS_ROOT = os.path.join(BASE_DIR, "Cover_pages")
METADATA_ROOT = os.path.join(BASE_DIR, "Meta_data")

os.makedirs(COVERS_ROOT, exist_ok=True)
os.makedirs(METADATA_ROOT, exist_ok=True)

HEADERS = {
    "User-Agent": "BookDatasetCollector/1.0 (contact: test@example.com)"
}

# 5 distinct categories
# SELECTED_CATEGORIES = [
#     "fantasy",
#     "mystery",
#     "thriller",
#     "historical_fiction",
#     "biography"
# ]
# SELECTED_CATEGORIES = [
#     "science_fiction",
#     "cyberpunk",
#     "horror",
#     "adventure",
#     "true_crime"
# ]
SELECTED_CATEGORIES = [
    "romance",
    "dystopian",
    "steampunk",
    "psychological_thriller",
    "mythology"
]

def sanitize_filename(name):
    # Remove characters that are illegal in Windows filenames
    clean = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()
    return clean.replace(" ", "_")[:35]

def fetch_category_books(category_name, folder_prefix_idx, limit=20):
    # Category folder: 01_fantasy, 02_mystery, etc.
    formatted_folder_name = f"{folder_prefix_idx:02d}_{category_name}"
    category_cover_dir = os.path.join(COVERS_ROOT, formatted_folder_name)
    os.makedirs(category_cover_dir, exist_ok=True)

    # Search for books from 2016-2026 sorted by newest
    url = f"https://openlibrary.org/search.json?q=subject:{category_name}+AND+first_publish_year:[2016+TO+2026]&sort=new&limit={limit * 3}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"Failed to fetch {category_name}: HTTP {response.status_code}")
            return []

        docs = response.json().get("docs", [])
        saved_books_meta = []
        saved_count = 0

        for doc in docs:
            if saved_count >= limit:
                break

            cover_id = doc.get("cover_i")
            title = doc.get("title", "Unknown_Title")
            
            # Skip records without a valid cover
            if not cover_id:
                continue

            # Format image name as 01_Title.jpg, 02_Title.jpg, etc.
            clean_title = sanitize_filename(title)
            image_filename = f"{(saved_count + 1):02d}_{clean_title}.jpg"
            image_filepath = os.path.join(category_cover_dir, image_filename)

            cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"

            # Download Cover Image
            is_downloaded = False
            try:
                img_res = requests.get(cover_url, headers=HEADERS, timeout=10)
                if img_res.status_code == 200 and len(img_res.content) > 1000:
                    with open(image_filepath, "wb") as f:
                        f.write(img_res.content)
                    is_downloaded = True
            except Exception:
                is_downloaded = False

            if not is_downloaded:
                continue

            saved_count += 1

            # Fetch Book Description
            authors = doc.get("author_name", ["Unknown Author"])
            key = doc.get("key")
            publish_year = doc.get("first_publish_year") or (doc.get("publish_year", [None])[0])

            description = "No description available."
            if key:
                try:
                    desc_res = requests.get(f"https://openlibrary.org{key}.json", headers=HEADERS, timeout=5)
                    if desc_res.status_code == 200:
                        raw_desc = desc_res.json().get("description")
                        if isinstance(raw_desc, dict):
                            description = raw_desc.get("value", description)
                        elif isinstance(raw_desc, str):
                            description = raw_desc
                except Exception:
                    pass

            if description == "No description available." and doc.get("first_sentence"):
                first_sent = doc.get("first_sentence")
                description = first_sent.get("value") if isinstance(first_sent, dict) else str(first_sent)

            book_record = {
                "index": saved_count,
                "title": title,
                "authors": authors if isinstance(authors, list) else [authors],
                "publish_year": publish_year,
                "description": description,
                "cover_url": cover_url,
                "cover_filename": image_filename,
                "local_path": f"Cover_pages\\{formatted_folder_name}\\{image_filename}"
            }

            saved_books_meta.append(book_record)
            print(f"  [{saved_count:02d}/{limit}] Saved: {image_filename} ({publish_year})")
            time.sleep(0.15)

        # Save metadata JSON for this category
        metadata_filename = f"{formatted_folder_name}_metadata.json"
        metadata_filepath = os.path.join(METADATA_ROOT, metadata_filename)
        with open(metadata_filepath, "w", encoding="utf-8") as f:
            json.dump(saved_books_meta, f, indent=4, ensure_ascii=False)

        return saved_books_meta

    except Exception as e:
        print(f"Error processing {category_name}: {e}")
        return []

def main():
    print("Starting book data download for 5 categories (20 books each)...\n")
    
    for idx, category in enumerate(SELECTED_CATEGORIES, 1):
        print("=" * 65)
        print(f"[{idx:02d}/05] PROCESSING CATEGORY: {category.upper()}")
        print("=" * 65)
        
        fetch_category_books(category, folder_prefix_idx=idx, limit=20)
        time.sleep(0.5)

    print("\nExtraction completed successfully!")
    print(f"Covers saved at: {COVERS_ROOT}")
    print(f"Metadata saved at: {METADATA_ROOT}")

if __name__ == "__main__":
    main()