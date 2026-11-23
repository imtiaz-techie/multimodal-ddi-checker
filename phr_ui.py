import json
from pathlib import Path
from typing import Any

from rxlens_core import RxLensMedicineEngine
from rxlens_ddi import RxLensDDIEngine


class PHRManager:
    """Simple Personal Health Record (PHR) store backed by a local JSON file."""

    def __init__(self, storage_path: str = "phr_records.json") -> None:
        self.storage_path = Path(storage_path)
        self.data = self._load()

    def _default_data(self) -> dict[str, Any]:
        return {
            "patient": {"name": "", "age": None, "allergies": [], "conditions": []},
            "medications": [],
        }

    def _load(self) -> dict[str, Any]:
        if self.storage_path.exists():
            try:
                with self.storage_path.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    loaded.setdefault("patient", {"name": "", "age": None, "allergies": [], "conditions": []})
                    loaded.setdefault("medications", [])
                    return loaded
            except Exception:
                pass
        return self._default_data()

    def save(self) -> None:
        if not isinstance(self.data, dict):
            self.data = self._default_data()
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def set_patient_profile(
        self,
        name: str,
        age: int | None = None,
        allergies: list[str] | None = None,
        conditions: list[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(self.data, dict):
            self.data = self._default_data()
        self.data["patient"] = {
            "name": (name or "").strip(),
            "age": age,
            "allergies": [a.strip() for a in (allergies or []) if a and a.strip()],
            "conditions": [c.strip() for c in (conditions or []) if c and c.strip()],
        }
        self.save()
        return self.data["patient"]

    def add_medication(
        self, medicine_input: str, dosage: str = "", schedule: str = ""
    ) -> list[dict[str, str]]:
        if not isinstance(self.data, dict):
            self.data = self._default_data()
        meds = self.data.get("medications")
        if not isinstance(meds, list):
            meds = []
            self.data["medications"] = meds

        clean_med = (medicine_input or "").strip()
        if not clean_med:
            return meds

        entry = {
            "medicine": clean_med,
            "dosage": (dosage or "").strip(),
            "schedule": (schedule or "").strip(),
        }
        existing_names = {
            str(m.get("medicine", "")).lower()
            for m in meds
            if isinstance(m, dict)
        }
        if clean_med.lower() not in existing_names:
            meds.append(entry)
            self.save()
        return meds

    def remove_medication(self, medicine_name: str) -> list[dict[str, str]]:
        if not isinstance(self.data, dict):
            self.data = self._default_data()
        meds = self.data.get("medications") or []
        target = (medicine_name or "").strip().lower()
        self.data["medications"] = [
            m for m in meds
            if isinstance(m, dict) and str(m.get("medicine", "")).lower() != target
        ]
        self.save()
        return self.data["medications"]

    def get_summary(self) -> dict[str, Any]:
        if not isinstance(self.data, dict):
            self.data = self._default_data()
        return self.data


class RxLensPHRUI:
    """Interactive CLI / helper interface connecting PHR with Core & DDI Engines."""

    def __init__(
        self,
        medicine_csv_path: str = "medicine.csv",
        generic_csv_path: str = "generic.csv",
    ) -> None:
        self.engine = RxLensMedicineEngine(
            medicine_csv_path=medicine_csv_path,
            generic_csv_path=generic_csv_path,
        )
        self.ddi_engine = RxLensDDIEngine(core_engine=self.engine)
        self.phr = PHRManager()

    def lookup_medicine(self, query: str) -> dict[str, Any]:
        resolved = self.ddi_engine.resolve_medicine(query) or {}
        generic_key = resolved.get("generic") if isinstance(resolved, dict) else None
        generic_info = None
        if generic_key and callable(getattr(self.engine, "get_generic_info", None)):
            try:
                generic_info = self.engine.get_generic_info(generic_key)
            except Exception:
                generic_info = None

        alternatives = []
        if isinstance(resolved, dict) and resolved.get("matched") and callable(
            getattr(self.engine, "get_alternatives", None)
        ):
            try:
                alternatives = self.engine.get_alternatives(query)
            except Exception:
                alternatives = []

        return {
            "query": query,
            "resolved": resolved,
            "generic_info": generic_info,
            "alternatives": alternatives,
        }

    def run_ddi_check(self, prescription_text: str = "") -> dict[str, Any]:
        phr_data = self.phr.data if isinstance(self.phr.data, dict) else {}
        patient = phr_data.get("patient") if isinstance(phr_data.get("patient"), dict) else {}
        raw_meds = phr_data.get("medications") if isinstance(phr_data.get("medications"), list) else []
        phr_meds = [
            m.get("medicine", "")
            for m in raw_meds
            if isinstance(m, dict) and m.get("medicine")
        ]

        report = self.ddi_engine.check_interactions(
            medications=phr_meds,
            prescription_text=prescription_text or "",
            allergies=patient.get("allergies") or [],
            conditions=patient.get("conditions") or [],
        )
        if not isinstance(report, dict):
            return {
                "consolidated_medications": [],
                "ddi_alerts": [],
                "allergy_alerts": [],
                "condition_warnings": [],
                "has_risk": False,
            }
        return report

    def run_cli(self) -> None:
        print("=== RxLens AI - PHR, Medicine Lookup & DDI Checker ===")
        while True:
            print("\n1. Set Patient Profile")
            print("2. Add Medication to PHR")
            print("3. View PHR Summary")
            print("4. Lookup Medicine Info & Alternatives")
            print("5. Consolidate Prescription & Check DDI")
            print("6. Exit")
            choice = input("Choose an option (1-6): ").strip()

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
                rx_text = input("Paste prescription text (optional, press Enter to skip): ").strip()
                report = self.run_ddi_check(prescription_text=rx_text)
                print(json.dumps(report, indent=2, ensure_ascii=False, default=str))

            elif choice == "6":
                print("Exiting PHR & UI module.")
                break
            else:
                print("Invalid option. Please enter 1 to 6.")


if __name__ == "__main__":
    ui = RxLensPHRUI()
    ui.run_cli()
