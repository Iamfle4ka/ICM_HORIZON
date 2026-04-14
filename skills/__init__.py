"""
SkillsRegistry — skills/__init__.py
Načítá a verzuje YAML skill soubory pro LLM uzly.
Cachuje načtené soubory (čte disk pouze jednou).
"""

import hashlib
import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

# Absolutní cesta ke složce skills/
_SKILLS_DIR = Path(__file__).parent


class SkillsRegistry:
    """
    Singleton registry pro YAML skill soubory.

    Použití:
        registry = SkillsRegistry()
        skill = registry.get("maker_skill")
        prompt = skill["prompt"]
        version = registry.get_version("maker_skill")
        ph = registry.get_prompt_hash("maker_skill")
    """

    _instance: "SkillsRegistry | None" = None
    _cache: dict[str, dict] = {}

    def __new__(cls) -> "SkillsRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
        return cls._instance

    def get(self, name: str) -> dict:
        """
        Vrátí skill dict pro daný název.
        Načte ze souboru pokud ještě není v cache.

        Args:
            name: Název skill souboru bez přípony (např. "maker_skill")

        Returns:
            dict se všemi YAML klíči: name, version, prompt, constraints, ...

        Raises:
            FileNotFoundError: Pokud skill soubor neexistuje.
            ValueError: Pokud YAML je nevalidní.
        """
        if name in self._cache:
            return self._cache[name]

        skill_path = _SKILLS_DIR / f"{name}.yaml"
        if not skill_path.exists():
            raise FileNotFoundError(
                f"Skill soubor nenalezen: {skill_path}. "
                f"Dostupné soubory: {list(_SKILLS_DIR.glob('*.yaml'))}"
            )

        log.info(f"[SkillsRegistry] Načítám skill | name={name} | path={skill_path}")
        with skill_path.open("r", encoding="utf-8") as f:
            skill_data = yaml.safe_load(f)

        if not isinstance(skill_data, dict):
            raise ValueError(f"Neplatný YAML formát pro skill: {name}")

        required_keys = {"name", "version", "prompt", "node_type"}
        missing = required_keys - skill_data.keys()
        if missing:
            raise ValueError(f"Skill {name} chybí povinné klíče: {missing}")

        self._cache[name] = skill_data
        log.info(
            f"[SkillsRegistry] Skill načten | name={name} "
            f"version={skill_data['version']} node_type={skill_data['node_type']}"
        )
        return skill_data

    def get_prompt(self, name: str) -> str:
        """Vrátí prompt text pro daný skill."""
        return self.get(name)["prompt"]

    def get_prompt_hash(self, name: str) -> str:
        """
        Vrátí sha256[:12] hash promptu.
        Použití: pro audit trail a UI zobrazení.
        """
        prompt = self.get_prompt(name)
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]

    def get_version(self, name: str) -> str:
        """Vrátí verzi skill souboru."""
        return self.get(name)["version"]

    def get_all_skills(self) -> list[dict]:
        """
        Vrátí seznam všech dostupných skills s metadaty.
        Použití: pro UI stránku Nastavení → Skills Library.
        """
        skills = []
        for yaml_file in sorted(_SKILLS_DIR.glob("*.yaml")):
            name = yaml_file.stem
            try:
                skill = self.get(name)
                skills.append({
                    "name":         skill.get("name", name),
                    "skill_key":    name,
                    "version":      skill.get("version", "N/A"),
                    "author":       skill.get("author", "N/A"),
                    "approved_by":  skill.get("approved_by", "N/A"),
                    "approved_at":  skill.get("approved_at", "N/A"),
                    "node_type":    skill.get("node_type", "N/A"),
                    "prompt_hash":  self.get_prompt_hash(name),
                    "constraints":  skill.get("constraints", []),
                })
            except Exception as e:
                log.warning(f"[SkillsRegistry] Nelze načíst skill {name}: {e}")
        return skills

    def list_skills(self) -> list[dict]:
        """Alias pro get_all_skills() — kompatibilita s CONTINUATION_PROMPT."""
        return self.get_all_skills()

    def clear_cache(self) -> None:
        """Vyčistí cache (pro testování)."""
        self._cache.clear()
        log.info("[SkillsRegistry] Cache vyčištěna")


# Globální instance (singleton)
registry = SkillsRegistry()


if __name__ == "__main__":
    # Smoke test
    reg = SkillsRegistry()
    skills = reg.get_all_skills()
    print(f"Načteno {len(skills)} skills:")
    for s in skills:
        print(f"  {s['skill_key']} v{s['version']} [{s['node_type']}] hash={s['prompt_hash']}")

    # Test get
    maker = reg.get("maker_skill")
    assert maker["name"] == "maker_skill"
    assert maker["version"] == "3.2"
    assert len(reg.get_prompt_hash("maker_skill")) == 12

    print("OK — skills/__init__.py smoke test passed")
