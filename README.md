# Pseudo Connect

A college portal for asking doubts without the fear of being judged.

Students sign in with a registered `@college.edu` mail, pick Java / Web Dev / Maths / Physics, and can keep an alias in front of teachers. Admin still sees the real name so foul language and misuse can be handled.

## Run

```bash
cd ~/pseudo-connect
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Open [http://127.0.0.1:5050](http://127.0.0.1:5050).

## Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Student | rahul@college.edu | student123 |
| Student | ananya@college.edu | student123 |
| Student | priya@college.edu | student123 |
| Java teacher | java.faculty@college.edu | teacher123 |
| Web Dev teacher | web.faculty@college.edu | teacher123 |
| Maths teacher | maths.faculty@college.edu | teacher123 |
| Physics teacher | physics.faculty@college.edu | teacher123 |
| Admin | admin@college.edu | admin123 |

Only registered college emails are accepted. Data lives in `data/pseudo_connect.db`; uploads in `data/uploads/`.
