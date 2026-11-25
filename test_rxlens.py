from rxlens_core import RxLensMedicineEngine
from rxlens_ddi import RxLensDDIEngine
from rxlens_ocr import build_ddi_input_text
from phr_ui import RxLensPHRUI


def run_all_tests():
    core = RxLensMedicineEngine("medicine.csv/medicine.csv", "generic.csv/generic.csv")
    ddi = RxLensDDIEngine(core)

    # 1. Brand-to-generic resolution check
    res_napa = ddi.resolve_medicine("Napa 500mg")
    assert res_napa["matched"] is True, "Napa 500mg should match"
    assert "paracetamol" in str(res_napa["generic"]).lower(), f"Unexpected generic: {res_napa}"

    # 2. OCR/prescription text -> DDI check with existing PHR medication
    ui = RxLensPHRUI("medicine.csv/medicine.csv", "generic.csv/generic.csv")
    ui.phr.set_patient_profile("Demo Patient", 42, ["penicillin"], ["kidney"])
    ui.phr.add_medication("Warfarin", "5mg", "0+0+1")

    raw_rx = "1. Tab. Ibuprofen 400mg 1+0+1 for 5 days\n2. Cap. Seclo 20mg 0+1+0"
    cleaned_rx = build_ddi_input_text(raw_rx)
    ddi_out = ui.run_ddi_check(cleaned_rx)

    assert isinstance(ddi_out, dict), "run_ddi_check should return a dict"
    assert len(ddi_out.get("ddi_alerts", [])) > 0, f"Expected DDI alert for Warfarin + Ibuprofen, got: {ddi_out}"

    # 3. Empty / non-medicine text edge case
    empty_out = ui.run_ddi_check("")
    assert isinstance(empty_out, dict), "Empty input should still return a dict safely"

    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("Sample DDI Alerts:", ddi_out.get("ddi_alerts"))
    print("Condition Warnings:", ddi_out.get("condition_warnings"))
    print("Allergy Alerts:", ddi_out.get("allergy_alerts"))


if __name__ == "__main__":
    run_all_tests()
