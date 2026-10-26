import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'project.db')


SEED_OPPORTUNITIES = [
    ("USA Computing Olympiad (USACO)", "USACO", "CS & Engineering", "virtual", "Nationwide", "Online algorithm contests and training with divisions from Bronze to Platinum.", "https://usaco.org"),
    ("Congressional App Challenge", "U.S. House of Representatives", "CS & Engineering", "virtual", "Nationwide", "Annual app-building competition for students in participating congressional districts.", "https://www.congressionalappchallenge.us"),
    ("Codeforces Contests", "Codeforces", "CS & Engineering", "virtual", "Nationwide", "Regular online competitive programming rounds open to anyone.", "https://codeforces.com"),
    ("Kaggle Competitions", "Kaggle", "CS & Engineering", "virtual", "Nationwide", "Data science and machine learning competitions and free learning courses.", "https://www.kaggle.com"),
    ("Technovation Girls", "Technovation", "CS & Engineering", "virtual", "Nationwide", "Girls build a mobile app or AI project that tackles a community problem.", "https://technovation.org"),
    ("FIRST Robotics Competition", "FIRST", "CS & Engineering", "in-person", "Nationwide", "Student robotics teams design, build and compete with robots; find a team near you.", "https://www.firstinspires.org"),
    ("American Mathematics Competitions (AMC)", "Mathematical Association of America", "Math & Science", "in-person", "Nationwide", "Multiple-choice math contests, usually taken at school, leading to AIME and USAMO.", "https://maa.org"),
    ("Science Olympiad", "Science Olympiad", "Math & Science", "in-person", "Nationwide", "School team competitions across many science and engineering events.", "https://www.soinc.org"),
    ("Regeneron Science Talent Search", "Society for Science", "Math & Science", "hybrid", "Nationwide", "Prestigious research competition for high school seniors with independent research projects.", "https://www.societyforscience.org/regeneron-sts"),
    ("Conrad Challenge", "Conrad Foundation", "Math & Science", "virtual", "Nationwide", "Teams create innovative products addressing real-world problems in science and technology.", "https://www.conradchallenge.org"),
    ("HOSA - Future Health Professionals", "HOSA", "Math & Science", "in-person", "Nationwide", "Health science student organization with chapters, competitive events and leadership roles.", "https://hosa.org"),
    ("National Speech & Debate Association", "NSDA", "Business & Civics", "in-person", "Nationwide", "Join your school's speech and debate team and compete in tournaments.", "https://www.speechanddebate.org"),
    ("DECA", "DECA Inc.", "Business & Civics", "in-person", "Nationwide", "Business, marketing and entrepreneurship competitions through school chapters.", "https://www.deca.org"),
    ("FBLA (Future Business Leaders of America)", "FBLA", "Business & Civics", "in-person", "Nationwide", "Business career organization with chapters, competitive events and leadership roles.", "https://www.fbla.org"),
    ("U.S. Senate Youth Program", "U.S. Senate Youth Program", "Business & Civics", "in-person", "Nationwide", "Selective civic leadership program; state-level nomination required.", "https://ussenateyouth.org"),
    ("National History Day", "National History Day", "Arts & Humanities", "hybrid", "Nationwide", "Research-based history projects judged at district, state and national levels.", "https://www.nhd.org"),
    ("Scholastic Art & Writing Awards", "Alliance for Young Artists & Writers", "Arts & Humanities", "virtual", "Nationwide", "Recognition program for teen visual artists and writers; submissions through regional affiliates.", "https://www.artandwriting.org"),
    ("Girl Scout Gold Award", "Girl Scouts of the USA", "Service & Leadership", "in-person", "Nationwide", "Highest Girl Scout award, based on a sustainable community-impact project.", "https://www.girlscouts.org"),
    ("Eagle Scout Rank", "Scouting America", "Service & Leadership", "in-person", "Nationwide", "Highest Scouting rank, including a service project that the scout leads.", "https://www.scouting.org"),
    ("Key Club", "Kiwanis International", "Service & Leadership", "in-person", "Nationwide", "Student-led service organization with school chapters and leadership officer roles.", "https://www.keyclub.org"),
    ("National Honor Society", "NASSP", "Service & Leadership", "in-person", "Nationwide", "Recognizes scholarship, service, leadership and character through school chapters.", "https://www.nhs.us"),
    ("Roots & Shoots", "Jane Goodall Institute", "Service & Leadership", "hybrid", "Nationwide", "Youth-led community and environmental service projects with global support network.", "https://www.rootsandshoots.org"),
    ("VolunteerMatch", "VolunteerMatch", "Service & Leadership", "hybrid", "Nationwide", "Search local and virtual volunteer openings by cause and zip code.", "https://www.volunteermatch.org"),
    ("Local hospital teen volunteer program", "Hospitals near you", "Service & Leadership", "in-person", "Local", "Many hospitals run teen volunteer programs; search the hospital's volunteer services page.", ""),
    ("Peer tutoring at school or library", "Your school or public library", "Service & Leadership", "hybrid", "Local", "Tutor younger students; ask your counselor or librarian how to start a program.", ""),
]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table to store main activities/nonprofits/clubs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            organization TEXT,
            category TEXT NOT NULL
        )
    ''')

    # Columns added after the first version of the table
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(activities)")}
    for column, ddl in [("hours_per_week", "INTEGER"), ("weeks_per_year", "INTEGER"),
                        ("description", "TEXT")]:
        if column not in existing:
            cursor.execute(f"ALTER TABLE activities ADD COLUMN {column} {ddl}")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            feed_token TEXT NOT NULL UNIQUE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deadlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            details TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            title TEXT NOT NULL,
            organization TEXT NOT NULL,
            category TEXT NOT NULL,
            format TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT,
            url TEXT,
            deadline TEXT
        )
    ''')
    # user_id NULL marks built-in listings shared by everyone
    if cursor.execute("SELECT COUNT(*) FROM opportunities WHERE user_id IS NULL").fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO opportunities (title, organization, category, format, location, description, url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", SEED_OPPORTUNITIES)

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organizer_id INTEGER NOT NULL REFERENCES users(id),
            token TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            organization TEXT NOT NULL,
            category TEXT NOT NULL,
            event_date TEXT,
            hours INTEGER NOT NULL,
            description TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS event_checkins (
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            PRIMARY KEY (event_id, user_id)
        )
    ''')

    # Each user owns their own rows
    for table in ("activities", "deadlines"):
        cols = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
        if "user_id" not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)")

    conn.commit()
    conn.close()
    print("Database initialized successfully!")

if __name__ == '__main__':
    init_db()
