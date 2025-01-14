# FlatBot

FlatBot is your ultimate flat-hunting assistant! Designed to automate the tedious process of apartment applications on ImmoScout24, FlatBot achieved the impossible: it helped me secure my dream flat in Berlin. 🏡✨

## Description

FlatBot leverages ImmoScout24's instant email notifications to streamline your flat-hunting process. It constantly monitors your inbox for new flat offering alerts, processes them, and sends customized application messages—all while you focus on more meaningful activities, like working, spending time with loved ones, or simply relaxing.

This is a personal project, built out of necessity, to make my Berlin flat search a little less frustrating and time-consuming. FlatBot fills a gap that, as of 2025, ImmoScout24 has yet to address—even for premium subscribers. Here's hoping they'll catch up soon!

### What it does

FlatBot follows this workflow every 1–2 minutes:

1. **EmailFetcher**:  
   - Scans unread emails in the mailbox.  
   - If the subject matches a flat offering, it extracts the expose link and stores it as a new offer in the database.  

2. **ImmoScout24 Processor**:  
   - Retrieves new offerings from the database.  
   - Opens a Chrome session and navigates to the expose link.  
   - Scrapes details from the listing, logs in if necessary, and applies using a customized template that addresses the real estate agent directly.  
   - Saves timestamps of each operation and offer details to the database for review.  

### Requisites

To run FlatBot, you’ll need:  
- **A computer** that you can ideally leave running 24/7. FlatBot was developed on Windows, but with a few tweaks, it should run on macOS and Linux too.
- **A mailbox** to receive email alerts, accessible by FlatBot via IMAP (POP3 can also work with minor code changes). It's best to set up a dedicated mailbox for your flat search.  
- **Immoscout mail alerts** Create one or more search fileters and enable the immediate notifiaction of new offers.
- A properly set up **Chrome Browser** and **Chromedriver**.  
- **A 2Captcha subscription**. A €2–3 balance should last at least a month.  
- *(Optional but recommended)* **DB Browser for SQLite**, which lets you review the data processed by FlatBot.  
- *(Optional but highly recommended)* **ImmoScout24 Premium subscription** for faster and more comprehensive access to offers.  

### Installation

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/<your-username>/FlatBot.git
   cd FlatBot
   ```

2. **Create a Virtual Environment:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Copy `example_env` to a `.env` file and customize it with your credentials and applicant details:
   ```env
   EMAIL_USER=<your-email>
   EMAIL_PASSWORD=<your-email-password>
   IMMOSCOUT_USER=<your-immoscout-username>
   IMMOSCOUT_PASSWORD=<your-immoscout-password>
   ```

5. **Application Template:**
   Edit `ApplicationTemplate.txt` to personalize your messages. FlatBot uses fields scraped from the expose to customize each application. If you’d like to add more customization, the logic is in `modules/ApplicationGenerator.py`.

6. **Run FlatBot:**
   You’re all set! Run FlatBot with the following command:
   ```bash
   python main.py
   ```
   FlatBot will start applying for you.

## Thanks

FlatBot was inspired by the amazing [FlatHunter project](https://github.com/flathunters/flathunter). Special thanks to its contributors for their innovative approach, especially for the captcha-solving implementation, which greatly influenced FlatBot's design.  


Happy Flat Hunting! 🏡✨
