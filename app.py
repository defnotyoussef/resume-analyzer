from flask import Flask, request, jsonify, send_from_directory, send_file
import fitz
from groq import Groq
import json
import re
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
import os

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    cv_file = request.files["cv"]
    job_description = request.form["job_description"]

    pdf = fitz.open(stream=cv_file.read(), filetype="pdf")
    cv_text = ""
    for page in pdf:
        cv_text += page.get_text()

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
         {"role": "system", "content": """You are an aggressive CV optimizer and expert recruiter.
Your job is to REWRITE the CV to maximize the candidate's match for the specific job description.

You MUST:
- Reword bullet points to use keywords and language from the job description
- Reorder skills to put the most relevant ones first
- Reframe job titles and experience to align with what the job is looking for
- Rewrite the summary to directly target this specific role
- Add relevant skills the candidate likely has but didn't mention based on their background
- Make the candidate sound as qualified as possible for THIS specific job

You are NOT just reformatting — you are strategically rewriting every section to maximize the match score.

Respond in valid JSON only, no backticks, using this exact format:
{
  "match_score": 75,
  "missing_skills": ["skill1", "skill2"],
  "improvements": ["what you changed and why", "what you changed and why"],
  "rewritten_cv": {
    "name": "Full Name",
    "contact": "City, Country  |  Phone  |  Email  |  LinkedIn",
    "summary": "Summary rewritten to target this specific job",
    "skills": {
      "Category": "most relevant skills first"
    },
    "experience": [
      {
        "title": "Job Title",
        "company": "Company Name",
        "date": "Jan 2024 - Present",
        "location": "City, Country",
        "bullets": ["rewritten bullet using job keywords", "another bullet"]
      }
    ],
    "projects": [
      {
        "name": "Project Name",
        "tech": "Tech Stack",
        "bullets": ["rewritten to highlight relevance to the job"]
      }
    ],
    "education": [
      {
        "degree": "Degree Name",
        "institution": "University",
        "date": "2020 - 2024",
        "location": "City, Country"
      }
    ]
  }
}"""},
            {"role": "user", "content": f"CV:\n{cv_text}\n\nJOB DESCRIPTION:\n{job_description}"}
        ],
        temperature=0.7,
        max_tokens=2000
    )

    raw = response.choices[0].message.content
    clean = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(clean)
    except json.JSONDecodeError:
        clean = re.sub(r'[\x00-\x1f\x7f]', ' ', clean)
        result = json.loads(clean)

    return jsonify(result)

@app.route("/download", methods=["POST"])
def download():
    cv = request.json["rewritten_cv"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=0.7*inch, leftMargin=0.7*inch,
                            topMargin=0.6*inch, bottomMargin=0.6*inch)

    from reportlab.lib import colors
    from reportlab.platypus import HRFlowable, Table, TableStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    name_style = ParagraphStyle("name", fontSize=24, fontName="Helvetica-Bold",
                                alignment=TA_CENTER, spaceAfter=4,
                                textColor=colors.HexColor("#1a1a2e"))
    contact_style = ParagraphStyle("contact", fontSize=9, fontName="Helvetica",
                                   alignment=TA_CENTER, spaceAfter=14,
                                   textColor=colors.HexColor("#555555"))
    section_style = ParagraphStyle("section", fontSize=10, fontName="Helvetica-Bold",
                                   spaceBefore=14, spaceAfter=3,
                                   textColor=colors.HexColor("#1a1a2e"))
    job_title_style = ParagraphStyle("job", fontSize=10, fontName="Helvetica-Bold",
                                     spaceBefore=8, spaceAfter=0,
                                     textColor=colors.HexColor("#1a1a2e"))
    meta_style = ParagraphStyle("meta", fontSize=9, fontName="Helvetica-Oblique",
                                spaceAfter=4, textColor=colors.HexColor("#777777"))
    bullet_style = ParagraphStyle("bullet", fontSize=9, fontName="Helvetica",
                                  leading=14, spaceAfter=2, leftIndent=12,
                                  textColor=colors.HexColor("#333333"))
    body_style = ParagraphStyle("body", fontSize=9, fontName="Helvetica",
                                leading=14, spaceAfter=4,
                                textColor=colors.HexColor("#333333"))
    skills_style = ParagraphStyle("skills", fontSize=9, fontName="Helvetica",
                                  leading=15, spaceAfter=2,
                                  textColor=colors.HexColor("#333333"))
    project_style = ParagraphStyle("proj", fontSize=10, fontName="Helvetica-Bold",
                                   spaceBefore=8, spaceAfter=2,
                                   textColor=colors.HexColor("#2d2d6e"))

    def add_section(title):
        story.append(Paragraph(title.upper(), section_style))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#cccccc"), spaceAfter=6))

    def add_row(left_text, right_text):
        left = Paragraph(left_text, job_title_style)
        right = Paragraph(right_text, ParagraphStyle("dr", fontSize=9,
                          fontName="Helvetica", alignment=TA_RIGHT,
                          textColor=colors.HexColor("#777777")))
        t = Table([[left, right]], colWidths=["70%", "30%"])
        t.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ]))
        story.append(t)

    story = []

    story.append(Paragraph(cv["name"], name_style))
    story.append(Spacer(1, 14))
    story.append(Paragraph(cv["contact"], contact_style))
    story.append(HRFlowable(width="100%", thickness=1.5,
                            color=colors.HexColor("#1a1a2e"), spaceAfter=10))

    add_section("Summary")
    story.append(Paragraph(cv["summary"], body_style))

    add_section("Skills")
    for category, skills in cv["skills"].items():
        story.append(Paragraph(f"<b>{category}:</b> {skills}", skills_style))

    add_section("Experience")
    for job in cv["experience"]:
        add_row(f"<b>{job['title']}</b> — {job['company']}", job["date"])
        story.append(Paragraph(job["location"], meta_style))
        for bullet in job["bullets"]:
            story.append(Paragraph(f"• {bullet}", bullet_style))

    add_section("Projects")
    for proj in cv["projects"]:
        story.append(Paragraph(proj["name"], project_style))
        story.append(Paragraph(f"<i>{proj['tech']}</i>", ParagraphStyle("tech",
            fontSize=8, fontName="Helvetica-Oblique", spaceAfter=3,
            textColor=colors.HexColor("#888888"))))
        for bullet in proj["bullets"]:
            story.append(Paragraph(f"• {bullet}", bullet_style))

    add_section("Education")
    for edu in cv["education"]:
        add_row(f"<b>{edu['degree']}</b>", edu["date"])
        story.append(Paragraph(f"{edu['institution']} — {edu['location']}", meta_style))

    doc.build(story)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True,
                     download_name="rewritten_cv.pdf",
                     mimetype="application/pdf")

@app.route("/cover-letter", methods=["POST"])
def cover_letter():
    data = request.json
    cv = data["cv"]
    job_description = data["job_description"]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": """You are an expert cover letter writer.
Write a compelling, personalized cover letter based on the CV and job description provided.
The cover letter should:
- Open with a strong hook that grabs attention
- Highlight the most relevant experience and skills for this specific job
- Show genuine enthusiasm for the role and company
- Be concise — 3 to 4 paragraphs max
- End with a confident call to action
- Sound human and natural, not generic or robotic
Return only the cover letter text, nothing else."""},
            {"role": "user", "content": f"CV:\n{json.dumps(cv)}\n\nJOB DESCRIPTION:\n{job_description}"}
        ],
        temperature=0.8,
        max_tokens=1000
    )

    letter = response.choices[0].message.content
    return jsonify({"cover_letter": letter})

@app.route("/download-cover-letter", methods=["POST"])
def download_cover_letter():
    text = request.json["cover_letter"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT

    styles = getSampleStyleSheet()

    date_style = ParagraphStyle("date", fontSize=10, fontName="Helvetica",
                                spaceAfter=20, textColor=colors.HexColor("#777777"))
    body_style = ParagraphStyle("body", fontSize=10, fontName="Helvetica",
                                leading=16, spaceAfter=12,
                                textColor=colors.HexColor("#1a1a1a"))
    closing_style = ParagraphStyle("closing", fontSize=10, fontName="Helvetica",
                                   spaceBefore=20, spaceAfter=40,
                                   textColor=colors.HexColor("#1a1a1a"))

    from datetime import date
    today = date.today().strftime("%B %d, %Y")

    story = []
    story.append(Paragraph(today, date_style))

    paragraphs = text.strip().split("\n\n")
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        if i == len(paragraphs) - 1:
            story.append(Paragraph(para, closing_style))
        else:
            story.append(Paragraph(para, body_style))

    doc.build(story)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True,
                     download_name="cover_letter.pdf",
                     mimetype="application/pdf")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)