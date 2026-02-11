
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

PSN = "RKE_Micky30"
URL = "https://gtsh-rank.com/profile/"

def main():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        print(f"Loading {URL}...")
        driver.get(URL)
        
        print(f"Searching for {PSN}...")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "psnid")))
        driver.find_element(By.ID, "psnid").send_keys(PSN)
        driver.find_element(By.XPATH, '//button[text()="GET"]').click()
        
        print("Waiting for result...")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "result")))
        
        # Check for error message
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "API not available" in body_text:
            print("❌ API Error detected.")
            return

        print("Attempting to find avatar...")
        try:
            # Try the standard selector first
            sel = "img.driver-photo"
            print(f"Looking for '{sel}'...")
            avatar_el = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            print("✅ Avatar found!")
            print(f"Src: {avatar_el.get_attribute('src')}")
            
            # Save it
            with open(f"{PSN}_debug.png", "wb") as f:
                f.write(avatar_el.screenshot_as_png)
            print("Saved screenshot.")
            
        except Exception as e:
            print(f"❌ Standard selector failed: {e}")
            
            # Dump page source to see what's there
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("Saved debug_page.html")
            
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
