import re
import pandas as pd
from rapidfuzz import fuzz, process


class RxLensMedicineEngine:
    def __init__(self, medicine_csv_path: str, generic_csv_path: str | None = None):
        self.med_df = pd.read_csv(medicine_csv_path, encoding="utf-8", encoding_errors="replace")
        self.gen_df = (
            pd.read_csv(generic_csv_path, encoding="utf-8", encoding_errors="replace")
            if generic_csv_path
            else None
        )

        for col in ["brand name", "generic", "strength", "dosage form", "manufacturer", "Package Size"]:
            if col in self.med_df.columns:
                self.med_df[f"{col}_norm"] = (
                    self.med_df[col]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                )

        if "Package Size" in self.med_df.columns:
            self.med_df["extracted_price"] = (
                self.med_df["Package Size"]
                .fillna("")
                .astype(str)
                .apply(self._extract_price_number)
            )
        else:
            self.med_df["extracted_price"] = None

        if self.gen_df is not None and "generic name" in self.gen_df.columns:
            self.gen_df["generic_name_norm"] = (
                self.gen_df["generic name"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
            )

    @staticmethod
    def _extract_price_number(text: str) -> float | None:
        match = re.search(r"(?:tk\.?|bdt|৳|price[:\s]*)\s*(\d+(?:\.\d+)?)", text.lower())
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def match_brand(self, query: str, threshold: int = 75) -> dict | None:
        if not query or "brand name_norm" not in self.med_df.columns:
            return None

        cleaned = query.strip().lower()
        choices = self.med_df["brand name_norm"].tolist()
        best = process.extractOne(cleaned, choices, scorer=fuzz.WRatio)

        if not best or best[1] < threshold:
            return None

        row = self.med_df.iloc[best[2]]
        return {
            "query": query,
            "matched_brand": row.get("brand name", ""),
            "type": row.get("type", ""),
            "generic": row.get("generic", ""),
            "strength": row.get("strength", ""),
            "dosage_form": row.get("dosage form", ""),
            "manufacturer": row.get("manufacturer", ""),
            "package_size": row.get("Package Size", ""),
            "extracted_price": row.get("extracted_price", None),
            "confidence": round(best[1], 2),
        }

    def get_generic_safety_info(self, generic_name: str) -> dict | None:
        if self.gen_df is None or not generic_name or "generic_name_norm" not in self.gen_df.columns:
            return None

        g_norm = generic_name.strip().lower()
        matches = self.gen_df[self.gen_df["generic_name_norm"] == g_norm]
        if matches.empty:
            matches = self.gen_df[self.gen_df["generic_name_norm"].str.contains(g_norm, na=False, regex=False)]

        if matches.empty:
            return None

        row = matches.iloc[0]
        return {
            "generic_name": row.get("generic name", ""),
            "drug_class": row.get("drug class", ""),
            "interaction_description": row.get("interaction description", ""),
            "contraindications_description": row.get("contraindications description", ""),
        }

    def find_equivalent_alternatives(self, brand_query: str, limit: int = 5) -> list[dict]:
        target = self.match_brand(brand_query)
        if not target:
            return []

        g_norm = str(target.get("generic", "")).strip().lower()
        s_norm = str(target.get("strength", "")).strip().lower()
        f_norm = str(target.get("dosage_form", "")).strip().lower()
        target_brand_norm = str(target.get("matched_brand", "")).strip().lower()

        df = self.med_df.copy()
        mask = pd.Series(True, index=df.index)

        if "generic_norm" in df.columns and g_norm:
            mask &= df["generic_norm"] == g_norm
        if "strength_norm" in df.columns and s_norm:
            mask &= df["strength_norm"] == s_norm
        if "dosage form_norm" in df.columns and f_norm:
            mask &= df["dosage form_norm"] == f_norm
        if "brand name_norm" in df.columns:
            mask &= df["brand name_norm"] != target_brand_norm

        candidates = df[mask].copy()
        if candidates.empty:
            return []

        if candidates["extracted_price"].notna().any():
            candidates = candidates.sort_values(by="extracted_price", ascending=True, na_position="last")

        results = []
        target_price = target.get("extracted_price")

        for _, row in candidates.head(limit).iterrows():
            alt_price = row.get("extracted_price")
            savings_pct = None
            if (
                target_price is not None
                and alt_price is not None
                and pd.notna(target_price)
                and pd.notna(alt_price)
                and float(target_price) > 0
            ):
                savings_pct = round(((float(target_price) - float(alt_price)) / float(target_price)) * 100, 1)

            results.append({
                "brand_name": row.get("brand name", ""),
                "generic": row.get("generic", ""),
                "strength": row.get("strength", ""),
                "dosage_form": row.get("dosage form", ""),
                "manufacturer": row.get("manufacturer", ""),
                "package_size": row.get("Package Size", ""),
                "extracted_price": alt_price if pd.notna(alt_price) else None,
                "savings_vs_matched_pct": savings_pct,
            })

        return results
