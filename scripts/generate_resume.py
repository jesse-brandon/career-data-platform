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


def load_skills():
    with open(SKILLS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def aggregate_skills(roles, skills_map):
    used_tech = set()

    for role in roles:
        achievements = role.get("filtered_achievements") or role.get("achievements", [])
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


@app.command()
def build(
    include: list[str] = typer.Option(
        None, "--include", "-i", help="Filter achievements by tag"
    ),
    output: str = typer.Option(
        "resume.md", "--output", "-o", help="Output markdown file"
    ),
):
    """
    Generate resume markdown from structured role data.
    """
    skills_map = load_skills()
    profile = load_profile()
    roles = load_roles()
    roles = filter_roles(roles, include)

    if not roles:
        typer.echo("No matching roles found.")
        raise typer.Exit()

    skills = aggregate_skills(roles, skills_map)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("base.md.j2")

    rendered = template.render(roles=roles, profile=profile, skills=skills)

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / output

    output_path.write_text(rendered, encoding="utf-8")

    typer.echo(f"Resume generated: {output_path}")


@app.command()
def version():
    typer.echo("Career Data Platform v1")


if __name__ == "__main__":
    app()
