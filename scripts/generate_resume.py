import subprocess
from datetime import datetime
from pathlib import Path

import typer
import yaml
from jinja2 import Environment, FileSystemLoader

app = typer.Typer()

DATA_DIR = Path("data/roles")
TEMPLATE_DIR = Path("templates")
OUTPUT_DIR = Path("outputs")
PROFILE_PATH = Path("data/profile.yaml")
SKILLS_PATH = Path("data/skills.yaml")
CERT_PATH = Path("data/certifications.yaml")


def load_certifications():
    with open(CERT_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ym_to_key(ym: str | None, ongoing: bool = False) -> int:
    if not ym:
        return 999912 if ongoing else 0
    y, m = ym.split("-")
    return int(y) * 100 + int(m)


def key_to_ym(key: int) -> str:
    y = key // 100
    m = key % 100
    return f"{y:04d}-{m:02d}"


def format_ym(ym: str | None) -> str:
    if not ym or ym == "Present":
        return "Present"
    dt = datetime.strptime(ym, "%Y-%m")
    return dt.strftime("%b %Y")


def load_skills():
    with open(SKILLS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def group_roles_for_display(roles: list[dict]) -> list[dict]:
    """
    Returns a list of display roles:
    - company
    - overall date window
    - entries (grouped roles)
    """

    groups: dict[str, dict] = {}
    singles: list[dict] = []

    for role in roles:
        group_id = role.get("display_group")
        if not group_id:
            singles.append(role)
            continue

        if group_id not in groups:
            groups[group_id] = {
                "display_group": group_id,
                "display_company": role.get("display_company") or role["company"],
                "entries": [],
            }

        groups[group_id]["entries"].append(role)

    display_roles: list[dict] = []

    # Build grouped display roles
    for g in groups.values():
        entries = g["entries"]

        # Sort entries within the group:
        # 1) explicit display_order
        # 2) most recent end_date
        entries_sorted = sorted(
            entries,
            key=lambda r: (
                r.get("display_order", 9999),
                -ym_to_key(r.get("end_date"), ongoing=True),
                -ym_to_key(r.get("start_date"), ongoing=False),
            ),
        )

        # Determine overall date range
        start_keys = [ym_to_key(r.get("start_date")) for r in entries_sorted]
        end_keys = [ym_to_key(r.get("end_date"), ongoing=True) for r in entries_sorted]

        start_min = min(start_keys)
        end_max = max(end_keys)

        start_str = key_to_ym(start_min)
        end_str = "Present" if end_max == 999912 else key_to_ym(end_max)

        display_roles.append(
            {
                "company": g["display_company"],
                "start_key": start_min,
                "end_key": end_max,
                "start_date": format_ym(start_str),
                "end_date": format_ym(end_str),
                "entries": entries_sorted,
            }
        )

    # Convert singles into display roles too (same shape)
    for r in singles:
        end_key = ym_to_key(r.get("end_date"), ongoing=True)

        display_roles.append(
            {
                "company": r.get("display_company") or r["company"],
                "start_key": ym_to_key(r.get("start_date")),
                "end_key": end_key,
                "start_date": format_ym(r.get("start_date")),
                "end_date": format_ym(r.get("end_date") or "Present"),
                "entries": [r],
            }
        )

    # Sort display roles: most recent end_key first, then start_key
    display_roles.sort(key=lambda d: (-d["end_key"], -d["start_key"], d["company"]))

    return display_roles


def aggregate_skills_from_display_roles(display_roles, skills_map):
    used_tech = set()

    for dr in display_roles:
        for entry in dr["entries"]:
            achievements = entry.get("filtered_achievements") or entry.get(
                "achievements", []
            )
            for ach in achievements:
                for tech in ach.get("technologies", []):
                    used_tech.add(tech)

    categorized = {}
    for category, skills in skills_map.items():
        matched = [skill for skill in skills if skill in used_tech]
        if matched:
            categorized[category] = sorted(matched)

    return categorized


def load_profile():
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_roles():
    roles = []

    for file in DATA_DIR.glob("*.yaml"):
        with open(file, "r", encoding="utf-8") as f:
            role = yaml.safe_load(f)
            roles.append(role)

    return roles


def filter_roles(roles, include_tags=None):
    if not include_tags:
        return roles

    filtered_roles = []

    for role in roles:
        filtered_achievements = []

        for ach in role.get("achievements", []):
            if any(tag in ach.get("tags", []) for tag in include_tags):
                filtered_achievements.append(ach)

        if filtered_achievements:
            role_copy = role.copy()
            role_copy["filtered_achievements"] = filtered_achievements
            filtered_roles.append(role_copy)

    return filtered_roles


def extract_keywords(text: str) -> set[str]:
    keywords = {
        "dagster",
        "kubernetes",
        "spark",
        "trino",
        "postgres",
        "aws",
        "gcp",
        "etl",
        "pipeline",
        "python",
        "docker",
        "kafka",
        "airflow",
    }

    text_lower = text.lower()

    found = set()

    for k in keywords:
        if k in text_lower:
            found.add(k)

    return found


@app.command()
def build(
    include: list[str] = typer.Option(
        None, "--include", "-i", help="Filter achievements by tag"
    ),
    output: str = typer.Option(
        "resume.md", "--output", "-o", help="Output markdown file"
    ),
    max_bullets: int = typer.Option(None, "--max-bullets", "-m"),
):
    """
    Generate resume markdown from structured role data.
    """
    skills_map = load_skills()
    profile = load_profile()
    roles = load_roles()
    roles = filter_roles(roles, include)
    certifications = load_certifications()

    if not isinstance(max_bullets, int):
        max_bullets = None

    if not roles:
        typer.echo("No matching roles found.")
        raise typer.Exit()

    display_roles = group_roles_for_display(roles)

    skills = aggregate_skills_from_display_roles(display_roles, skills_map)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("base.md.j2")

    for dr in display_roles:
        for entry in dr["entries"]:
            entry["start_date"] = format_ym(entry.get("start_date"))
            entry["end_date"] = format_ym(entry.get("end_date"))

    if max_bullets:
        for dr in display_roles:
            for entry in dr["entries"]:
                achievements = entry.get("filtered_achievements") or entry.get(
                    "achievements", []
                )
                entry["filtered_achievements"] = achievements[:max_bullets]

    rendered = template.render(
        display_roles=display_roles,
        profile=profile,
        skills=skills,
        certifications=certifications,
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / output

    output_path.write_text(rendered, encoding="utf-8")

    typer.echo(f"Resume generated: {output_path}")

    pdf_path = output_path.with_suffix(".pdf")

    try:
        subprocess.run(
            [
                "pandoc",
                str(output_path),
                "-o",
                str(pdf_path),
                "--pdf-engine=wkhtmltopdf",
                "-c",
                "templates/resume.css",
            ],
            check=True,
        )
        typer.echo(f"PDF generated: {pdf_path}")
    except Exception:
        typer.echo("Pandoc not available, skipping PDF generation.")


@app.command()
def version():
    typer.echo("Career Data Platform v1")


@app.command()
def target(
    job_file: str,
    output: str = typer.Option("target_resume.md", "--output", "-o"),
):
    """
    Generate resume tailored to a job description.
    """

    text = Path(job_file).read_text(encoding="utf-8")

    keywords = extract_keywords(text)

    typer.echo(f"Detected keywords: {', '.join(sorted(keywords))}")

    include_tags = list(keywords)

    build(include=include_tags, output=output)


if __name__ == "__main__":
    app()
