from playwright.sync_api import sync_playwright
from worker import ApplyWorker

def main():
    with sync_playwright() as p:
        worker = ApplyWorker(p)
        worker.start()

if __name__ == "__main__":
    main() 