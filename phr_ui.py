import json
from pathlib import Path
from typing import Any

from rxlens_core import RxLensMedicineEngine


class PHRManager:
    """Simple Personal Health Record (PHR) store backed by a local JSON file."""

    def __init__(self, storage_path: str = "phr_records.json") -> None:
        self.storage_path = Path(storage_path)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if self.storage_path.exists():
            with self.storage_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "patient": {"name": "", "age": None, "allergies": [], "conditions": []},
            "medications": [],
        }

    def save(self) -> None:
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def set_patient_profile(
        self,
        name: str,
        age: int | None = None,
        allergies: list[str] | None = None,
        conditions: list[str] | None = None,
    ) -> dict[str, Any]:
        self.data["patient"] = {
            "name": name.strip(),
            "age": age,
            "allergies": [a.strip() for a in (allergies or []) if a.strip()],
            "conditions": [c.strip() for c in (conditions or []) if c.strip()],
        }
        self.save()
        return self.data["patient"]

    def add_medication(
        self, medicine_input: str, dosage: str = "", schedule: str = ""
    ) -> list[dict[str, str]]:
        clean_med = medicine_input.strip()
        if not clean_med:
            return self.data["medications"]

        entry = {
            "medicine": clean_med,
            "dosage": dosage.strip(),
            "schedule": schedule.strip(),
        }
        existing_names = {m["medicine"].lower() for m in self.data["medications"]}
        if clean_med.lower() not in existing_names:
            self.data["medications"].append(entry)
            self.save()
        return self.data["medications"]

    def remove_medication(self, medicine_name: str) -> list[dict[str, str]]:
        target = medicine_name.strip().lower()
        self.data["medications"] = [
            m for m in self.data["medications"] if m["medicine"].lower() != target
        ]
        self.save()
        return self.data["medications"]

    def get_summary(self) -> dict[str, Any]:
        return self.data


class RxLensPHRUI:
    """Interactive CLI / helper interface connecting PHR with RxLensMedicineEngine."""

    def __init__(
        self,
        medicine_csv_path: str = "medicine.csv",
        generic_csv_path: str = "generic.csv",
    ) -> None:
        self.engine = RxLensMedicineEngine(
            medicine_csv_path=medicine_csv_path,
            generic_csv_path=generic_csv_path,
        )
        self.phr = PHRManager()

    def lookup_medicine(self, query: str) -> dict[str, Any]:
        match = None
        for method_name in ("find_medicine", "search_medicine", "lookup_medicine", "get_medicine"):
            fn = getattr(self.engine, method_name, None)
            if callable(fn):
                match = fn(query)
                break

        generic_key = match.get("generic") if isinstance(match, dict) else None
        generic_info = None
        if generic_key and callable(getattr(self.engine, "get_generic_info", None)):
            generic_info = self.engine.get_generic_info(generic_key)

        alternatives = []
        if match and callable(getattr(self.engine, "get_alternatives", None)):
            alternatives = self.engine.get_alternatives(query)

        return {
            "query": query,
            "match": match,
            "generic_info": generic_info,
            "alternatives": alternatives,
            "available_engine_methods": [
                m for m in dir(self.engine) if not m.startswith("_")
            ],
        }

    def run_cli(self) -> None:
        print("=== RxLens AI - PHR & Medicine Lookup ===")
        while True:
            print("\n1. Set Patient Profile")
            print("2. Add Medication to PHR")
            print("3. View PHR Summary")
            print("4. Lookup Medicine Info & Alternatives")
            print("5. Exit")
            choice = input("Choose an option (1-5): ").strip()

            if choice == "1":
                name = input("Patient name: ").strip()
                age_raw = input("Age (optional): ").strip()
                age = int(age_raw) if age_raw.isdigit() else None
                allergies = input("Allergies (comma separated): ").split(",")
                conditions = input("Conditions (comma separated): ").split(",")
                profile = self.phr.set_patient_profile(name, age, allergies, conditions)
                print("Saved profile:", profile)

            elif choice == "2":
                med = input("Medicine brand/name: ").strip()
                dosage = input("Dosage (e.g. 500mg): ").strip()
                schedule = input("Schedule (e.g. 1+0+1): ").strip()
                meds = self.phr.add_medication(med, dosage, schedule)
                print("Current medications:", meds)

            elif choice == "3":
                print(json.dumps(self.phr.get_summary(), indent=2, ensure_ascii=False))

            elif choice == "4":
                query = input("Enter medicine name to inspect: ").strip()
                result = self.lookup_medicine(query)
                print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

            elif choice == "5":
                print("Exiting PHR & UI module.")
                break
            else:
                print("Invalid option. Please enter 1 to 5.")


if __name__ == "__main__":
    ui = RxLensPHRUI()
    ui.run_cli()
