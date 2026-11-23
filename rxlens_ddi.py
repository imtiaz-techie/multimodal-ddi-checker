from __future__ import annotations

import re
from typing import Any


class RxLensDDIEngine:
    """Consolidates medicines/prescriptions and checks drug-drug & patient-risk interactions."""

    KNOWN_DDI_PAIRS: dict[frozenset[str], dict[str, str]] = {
        frozenset({"warfarin", "ibuprofen"}): {
            "severity": "High",
            "effect": "Increased risk of gastrointestinal and systemic bleeding.",
            "recommendation": "Avoid concurrent NSAID use with warfarin or monitor INR closely.",
        },
        frozenset({"warfarin", "aspirin"}): {
            "severity": "High",
            "effect": "Additive anticoagulant/antiplatelet effect increases bleeding risk.",
            "recommendation": "Consult physician before combining; watch for signs of bleeding.",
        },
        frozenset({"metformin", "alcohol"}): {
            "severity": "Moderate-High",
            "effect": "Increased risk of lactic acidosis and hypoglycemia.",
            "recommendation": "Avoid excessive alcohol intake while taking metformin.",
        },
        frozenset({"clarithromycin", "simvastatin"}): {
            "severity": "High",
            "effect": "Elevated statin levels increase risk of myopathy or rhabdomyolysis.",
            "recommendation": "Temporarily suspend simvastatin during clarithromycin therapy.",
        },
        frozenset({"ciprofloxacin", "tizanidine"}): {
            "severity": "High",
            "effect": "Markedly increased tizanidine concentration causing hypotension/sedation.",
            "recommendation": "Contraindicated; avoid co-administration.",
        },
        frozenset({"amoxicillin", "methotrexate"}): {
            "severity": "Moderate-High",
            "effect": "Reduced renal clearance of methotrexate may raise toxicity.",
            "recommendation": "Monitor for methotrexate toxicity if combined.",
        },
        frozenset({"omeprazole", "clopidogrel"}): {
            "severity": "Moderate",
            "effect": "May reduce antiplatelet activation of clopidogrel.",
            "recommendation": "Consider alternative acid suppressant (e.g., pantoprazole) if advised.",
        },
    }

    def __init__(self, core_engine: Any | None = None) -> None:
        self.core = core_engine

    def normalize_name(self, text: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            re.sub(r"[^a-zA-Z0-9\s+-]", " ", (text or "").lower()),
        ).strip()

    def extract_candidates_from_text(self, prescription_text: str) -> list[str]:
        if not prescription_text or not prescription_text.strip():
            return []

        cleaned = re.sub(
            r"\b(tab|cap|syr|inj|drop|gel|crm|mg|ml|mcg|gm|g|od|bd|tds|qid|1\+0\+1|0\+0\+1|1\+1\+1)\b",
            " ",
            prescription_text,
            flags=re.IGNORECASE,
        )
        tokens = [
            self.normalize_name(part)
            for part in re.split(r"[\n,;+/|]+", cleaned)
        ]
        results: list[str] = []
        seen: set[str] = set()
        for tok in tokens:
            tok = re.sub(r"\b\d+(\.\d+)?\b", "", tok).strip()
            if len(tok) >= 2 and tok not in seen:
                seen.add(tok)
                results.append(tok)
        return results

    def resolve_medicine(self, query: str) -> dict[str, Any]:
        q_norm = self.normalize_name(query)
        info: dict[str, Any] = {
            "input": query,
            "normalized": q_norm,
            "matched": False,
            "brand": query.strip(),
            "generic": q_norm,
            "raw": None,
        }

        if self.core is None:
            return info

        for method_name in (
            "find_medicine",
            "search_medicine",
            "lookup_medicine",
            "get_medicine",
            "match_medicine",
        ):
            fn = getattr(self.core, method_name, None)
            if callable(fn):
                try:
                    res = fn(query)
                    if res:
                        info["matched"] = True
                        info["raw"] = res
                        if isinstance(res, dict):
                            info["brand"] = (
                                res.get("brand")
                                or res.get("brand_name")
                                or res.get("medicine")
                                or res.get("name")
                                or info["brand"]
                            )
                            info["generic"] = self.normalize_name(
                                str(
                                    res.get("generic")
                                    or res.get("generic_name")
                                    or info["generic"]
                                )
                            )
                        return info
                except Exception:
                    pass

        med_df = getattr(self.core, "med_df", None)
        if med_df is not None and hasattr(med_df, "empty") and not med_df.empty:
            cols = [str(c) for c in med_df.columns]
            name_col = next(
                (c for c in cols if any(k in c.lower() for k in ("brand", "medicine", "name", "drug"))),
                cols[0],
            )
            gen_col = next(
                (c for c in cols if "generic" in c.lower() or "salt" in c.lower() or "composition" in c.lower()),
                None,
            )
            series_str = med_df[name_col].astype(str).str.lower()
            matched_rows = med_df[series_str == q_norm]
            if matched_rows.empty:
                matched_rows = med_df[series_str.str.contains(re.escape(q_norm), na=False)]

            if not matched_rows.empty:
                row = matched_rows.iloc[0].to_dict()
                info["matched"] = True
                info["raw"] = row
                info["brand"] = str(row.get(name_col, query.strip()))
                if gen_col and row.get(gen_col):
                    info["generic"] = self.normalize_name(str(row.get(gen_col)))
                return info

        return info

    def consolidate_medications(
        self,
        medications: list[str],
        prescription_text: str = "",
    ) -> dict[str, Any]:
        combined_inputs: list[str] = []
        for m in medications or []:
            if m and str(m).strip():
                combined_inputs.append(str(m).strip())
        if prescription_text:
            combined_inputs.extend(self.extract_candidates_from_text(prescription_text))

        consolidated: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        for item in combined_inputs:
            resolved = self.resolve_medicine(item)
            dedup_key = resolved["generic"] or resolved["normalized"]
            if dedup_key and dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                consolidated.append(resolved)

        return {
            "total_consolidated": len(consolidated),
            "medications": consolidated,
        }

    def check_interactions(
        self,
        medications: list[str],
        prescription_text: str = "",
        allergies: list[str] | None = None,
        conditions: list[str] | None = None,
    ) -> dict[str, Any]:
        cons = self.consolidate_medications(medications, prescription_text)
        med_items = cons["medications"]
        norm_generics = [m["generic"] for m in med_items if m.get("generic")]

        ddi_alerts: list[dict[str, str]] = []
        for i in range(len(norm_generics)):
            for j in range(i + 1, len(norm_generics)):
                g1, g2 = norm_generics[i], norm_generics[j]
                pair = frozenset({g1, g2})
                if pair in self.KNOWN_DDI_PAIRS:
                    rule = self.KNOWN_DDI_PAIRS[pair]
                    ddi_alerts.append(
                        {
                            "pair": f"{g1} + {g2}",
                            "severity": rule["severity"],
                            "effect": rule["effect"],
                            "recommendation": rule["recommendation"],
                        }
                    )
                else:
                    for rule_pair, rule in self.KNOWN_DDI_PAIRS.items():
                        items_list = list(rule_pair)
                        if len(items_list) == 2:
                            a, b = items_list[0], items_list
