import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL = "https://yagp.org/winners/#"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def clean_text(x):
    if x is None:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()

def is_probably_person(name: str) -> bool:
    name = clean_text(name)
    if not name:
        return False

    upper = name.upper()

    bad_exact_or_contains = [
        "ENSEMBLE", "ENSEMBLES", "PAS DE DEUX"
    ]
    if any(b in upper for b in bad_exact_or_contains):
        return False

    if len(name.split()) == 1 and name.isupper():
        return False

    if len(name.split()) > 5:
        return False

    if not re.search(r"[A-Za-z]", name):
        return False

    return True

def parse_age(value):
    value = clean_text(value)
    if re.fullmatch(r"\d{1,2}", value):
        return value
    return ""

def get_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1800,1400")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver

def collect_year_links(start_year=2000, end_year=2026, headless=True):
    driver = get_driver(headless=headless)
    wait = WebDriverWait(driver, 20)

    collected = []

    try:
        driver.get(BASE_URL)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(4)

        for year in range(start_year, end_year + 1):
            print(f"Collecting links for year {year}...")

            clicked = False

            # try direct click by link/button text
            xpath_options = [
                f"//*[normalize-space(text())='{year}']",
                f"//a[contains(normalize-space(.), '{year}')]",
                f"//button[contains(normalize-space(.), '{year}')]",
            ]

            for xp in xpath_options:
                try:
                    elem = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
                    driver.execute_script("arguments[0].click();", elem)
                    clicked = True
                    break
                except:
                    pass

            # fallback: page through navigation arrows if needed
            if not clicked:
                for _ in range(60):
                    try:
                        elem = driver.find_element(By.XPATH, f"//*[normalize-space(text())='{year}']")
                        driver.execute_script("arguments[0].click();", elem)
                        clicked = True
                        break
                    except:
                        pass

                    try:
                        next_btn = driver.find_element(By.XPATH, "//*[normalize-space(text())='>']")
                        driver.execute_script("arguments[0].click();", next_btn)
                        time.sleep(1.2)
                    except:
                        break

            time.sleep(3)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            links = set()
            for a in soup.find_all("a", href=True):
                href = urljoin("https://yagp.org", a["href"])
                text = clean_text(a.get_text(" ", strip=True))

                if "yagp.org" in href and (
                    "-winners/" in href
                    or href.rstrip("/").endswith("winners")
                    or "winner" in href.lower()
                ):
                    if href.rstrip("/") not in {
                        "https://yagp.org/winners",
                        "https://yagp.org/winners#",
                    }:
                        links.add((year, href, text))

            for year_val, href, text in sorted(links):
                collected.append({
                    "browse_year": year_val,
                    "detail_url": href,
                    "link_text": text
                })

    finally:
        driver.quit()

    return pd.DataFrame(collected).drop_duplicates()

def scrape_winner_page(url):
    print(f"Scraping page: {url}")
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")

    year_match = re.search(r"\b(20\d{2})\b", title + " " + url)
    page_year = year_match.group(1) if year_match else ""

    city_guess = ""
    m = re.search(r"YAGP\s+\d{4}\s+[–-]\s+(.*?)\s+[–-]\s+WINNERS", title, flags=re.I)
    if m:
        city_guess = clean_text(m.group(1))

    raw_lines = [clean_text(x) for x in soup.get_text("\n").splitlines()]
    lines = [x for x in raw_lines if x]

    current_division = ""
    current_category = ""
    records = []

    division_markers = [
        "SENIOR AGE DIVISION",
        "JUNIOR AGE DIVISION",
        "PRE-COMPETITIVE AGE DIVISION",
    ]
    category_markers = [
        "CLASSICAL DANCE CATEGORY",
        "CONTEMPORARY DANCE CATEGORY",
    ]

    award_like = re.compile(
        r"^(GRAND PRIX|YOUTH GRAND PRIX|HOPE AWARD|1ST PLACE|2ND PLACE|3RD PLACE|TOP \d+)",
        flags=re.I
    )

    i = 0
    while i < len(lines):
        line = lines[i]
        upper = line.upper()

        if any(marker in upper for marker in division_markers):
            current_division = line
            i += 1
            continue

        if any(marker in upper for marker in category_markers):
            current_category = line
            i += 1
            continue

        if award_like.search(line):
            award = line
            name = lines[i + 1] if i + 1 < len(lines) else ""
            age = lines[i + 2] if i + 2 < len(lines) else ""
            school = lines[i + 3] if i + 3 < len(lines) else ""

            age_clean = parse_age(age)
            if not age_clean:
                school = age
                age_clean = ""

            if is_probably_person(name):
                records.append({
                    "page_url": url,
                    "page_title": title,
                    "year": page_year,
                    "city": city_guess,
                    "division": current_division,
                    "dance_category": current_category,
                    "award": award,
                    "name": name,
                    "age": age_clean,
                    "school_company": school,
                })

            i += 4
            continue

        i += 1

    return pd.DataFrame(records).drop_duplicates()

def scrape_yagp_winners(start_year=2000, end_year=2026, headless=True):
    links_df = collect_year_links(start_year, end_year, headless=headless)

    print("\nCollected links:")
    print(links_df.head(20))
    print(f"\nTotal unique links: {links_df['detail_url'].nunique()}")

    all_pages = []
    for url in links_df["detail_url"].dropna().unique():
        try:
            df_page = scrape_winner_page(url)
            if not df_page.empty:
                all_pages.append(df_page)
        except Exception as e:
            print(f"FAILED on {url}: {e}")

    if all_pages:
        winners = pd.concat(all_pages, ignore_index=True).drop_duplicates()
    else:
        winners = pd.DataFrame(columns=[
            "page_url", "page_title", "year", "city", "division",
            "dance_category", "award", "name", "age", "school_company"
        ])

    winners = winners[winners["name"].apply(is_probably_person)].copy()
    winners = winners.drop_duplicates().reset_index(drop=True)

    return links_df, winners