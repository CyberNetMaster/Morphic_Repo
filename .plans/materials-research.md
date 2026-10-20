# Materials research log (2026-10-20)

Rule: a value is listed only if it was read on a fetched page or in a downloaded PDF.
"direct" = read in the maker's own TDS/MDS. "third-party" = read on a page not run by the maker.
Downloaded files live in `.plans/dl/materials/`.

## Downloaded files

| File | Source URL | What it is |
|---|---|---|
| `pla_zip/Prusament PLA/1_PLA_Prusament_TDS_2022_EN.pdf` | https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2024/05/7ca620c4-prusament-pla-plablend.zip | Prusament PLA TDS v1.1 (27-07-2022), official zip from prusament.com |
| `prusament_pla_mh.pdf` | https://www.matterhackers.com/r/xFvGl8 | Same PLA TDS, reseller-hosted copy (identical text) |
| `prusament_petg_official.pdf` | https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/9f8d2165-tds_prusament-petg_n_en.pdf | Prusament PETG TDS v1.1 (16-02-2022), official |
| `prusament_petg_3dpg.pdf` | https://www.3dprintergear.com.au/assets/files/technical-data-sheet%20(1).pdf | Same PETG TDS, reseller copy |
| `pa6cf20_v1.1.pdf` | https://fiberon.polymaker.com/wp-content/uploads/TDS_FIBERON-PA6-CF20_V1.1_EN.pdf | Polymaker Fiberon PA6-CF20 TDS V1.1, official |
| `eos_ti64.pdf` | https://www.eos.info/05-datasheet-images/Assets_MDS_Metal/EOS_Titanium_Ti64/Material_DataSheet_EOS_Titanium_Ti64_EOSM290_EOSM300-4_EOSM400_EOSM400-4_en.pdf | EOS Ti64 MDS bundle (M290 06.2022; 400W 07.2022; FlexLine M400 2017; more) |
| `alsi_4b4e1032.pdf` (+ `alsi_eos_archived.txt`) | https://web.archive.org/web/20250709102926id_/https://www.eos.info/var/assets/05-datasheet-images/Assets_MDS_Metal/EOS_Aluminium_AlSi10Mg/Material_Datasheet_EOS_Aluminium_AlSi10Mg_EN.pdf?v=6 | EOS AlSi10Mg MDS, 47 pages, Wayback copy of the EOS PDF (live EOS URL gave 404) |
| `eos_alsi10mg_old_gpi_archive.pdf` | https://web.archive.org/web/20181227164805id_/https://gpiprototype.com/pdf/EOS_Aluminium_AlSi10Mg_en.pdf | EOS AlSi10Mg MDS "AD, WEIL / 05.2014", reseller-hosted copy via Wayback |
| `alsi_4be8551a.pdf` | https://cdn.techpilot.com/public/132713/documents/4b7c1a54-6356-48a4-9cda-7a02f7f11853/alsi10mg_9011-0024_m290_material_data_sheet_12-17_de.pdf | EOS AlSi10Mg FlexLine M290 sheet, German, CR507 v01 12.2017 (no modulus; not used) |
| `ultimaker_pla_official_v5.pdf` | https://um-support-files.ultimaker.com/materials/2.85mm/tds/PLA/Ultimaker-PLA-TDS-v5.00.pdf | Ultimaker PLA TDS (file says Version v2.00, 2022-04-20); used for Z knockdown |
| `ultimaker_petg.pdf` | https://um-support-files.ultimaker.com/materials/2.85mm/tds/PETG/Ultimaker-PETG-TDS-v1.00.pdf | Ultimaker PETG TDS v1.00 (2022-04-29); used for Z knockdown |
| `faes2015_pa12.pdf` | https://utw10945.utweb.utexas.edu/sites/default/files/2015/2015-69-Faes.pdf | Faes et al. 2015, SFF Symposium, PA2200 Poisson's ratio |

Dead or blocked URLs tried: https://www.eos.info/05-datasheet-images/Assets_MDS_Metal/EOS_Aluminium_AlSi10Mg/Material_Datasheet_EOS_Aluminium_AlSi10Mg_EN.pdf (404), https://prusament.com/media/2020/01/PLA_TechSheet_ENG.pdf (404), https://prusament.com/media/2020/01/PETG_TechSheet_ENG.pdf (404), matweb.com (403), metals.ulprospector.com (403), link.springer.com table (login redirect), dspace.mit.edu Farah 2016 PDF (429), opus.cloud1.lib.uts.edu.au PETG paper (404), amendate.atlassian.net Hexagon material table (JS only).

## pla (Prusament PLA)

| Field | Value | URL | Read how |
|---|---|---|---|
| E_xy | 2300 MPa (2.3 +/- 0.1 GPa, horizontal) | official PLA TDS zip (above), p.2 | direct |
| nu | 0.35 (100% infill, FDM PLA) | https://pmc.ncbi.nlm.nih.gov/articles/PMC10096656/ (Gawel et al. 2023, Table 1) | third-party literature |
| strength_xy | 51 MPa ("Tensile Yield Strength", horizontal, ISO 527-1) | official PLA TDS, p.2 | direct |
| strength_z | null. TDS "Vertical xz" = 59 +/- 2 MPa is an on-edge specimen. TDS "Interlayer Adhesion" = 17 +/- 3 MPa, in-house method | official PLA TDS, p.2 | direct (read, not used) |
| interlayer_shear | null (TDS "Interlayer Adhesion" is not labelled shear) | - | - |
| density | 1.24 g/cm3 (ISO 1183) | official PLA TDS, p.2 | direct |
| cost | 29.99 USD per 1 kg spool | https://prusament.com/materials/pla/ | direct (maker store) |
| z_knockdown | 0.73 = 33.1 / 45.5 (Ultimaker PLA, break XY vs Z) | Ultimaker PLA TDS (above) | third-party TDS |

## petg (Prusament PETG)

| Field | Value | URL | Read how |
|---|---|---|---|
| E_xy | 1500 MPa (1.5 +/- 0.1 GPa, horizontal) | official PETG TDS PDF, p.2 | direct |
| nu | 0.4 (model input, not measured) | https://pmc.ncbi.nlm.nih.gov/articles/PMC6680790/ (Guessasma et al. 2019) | third-party literature |
| strength_xy | 47 MPa ("Tensile Yield Strength", horizontal, ISO 527-1) | official PETG TDS, p.2 | direct |
| strength_z | null. TDS "Vertical xz" = 50 +/- 1 MPa (on-edge). "Interlayer Adhesion" = 18 +/- 4 MPa | official PETG TDS, p.2 | direct (read, not used) |
| interlayer_shear | null | - | - |
| density | 1.27 g/cm3 (ISO 1183) | official PETG TDS, p.2 | direct |
| cost | 29.99 USD per 1 kg spool | https://prusament.com/materials/prusament-petg/ | direct (maker store) |
| z_knockdown | 0.49 = 19.0 / 38.5 (Ultimaker PETG, break XY vs Z) | Ultimaker PETG TDS (above) | third-party TDS |

## pa6cf (Polymaker Fiberon PA6-CF20)

| Field | Value | URL | Read how |
|---|---|---|---|
| E_xy | 8636.5 +/- 211.4 MPa (dry, X-Y, ISO 527) | Polymaker TDS V1.1 | direct |
| nu | 0.40 (Markforged Onyx, parallel orientation) | https://pmc.ncbi.nlm.nih.gov/articles/PMC10096896/ (Fisher et al. 2023, Table 2) | third-party literature |
| strength_xy | 109.3 +/- 2.4 MPa (dry, X-Y tensile) | Polymaker TDS V1.1 | direct |
| strength_z | 54.0 +/- 5.2 MPa (dry, Z tensile) | Polymaker TDS V1.1 | direct |
| wet values (not used) | E X-Y 2508.1, tensile X-Y 54.7, Z 25.5 MPa | Polymaker TDS V1.1 | direct |
| interlayer_shear | null | - | - |
| density | 1.17 g/cm3 at 23 C (ISO 1183) | Polymaker TDS V1.1 | direct |
| cost | 52.99 USD per 1 kg (SKU FG03003) | https://shop.polymaker.com/products/fiberon-pa6-cf20.json | direct (maker store JSON) |
| moisture condition | "MECHANICAL PROPERTIES - DRY STATUS" and "WET STATUS" tables; dry used | Polymaker TDS V1.1 | direct |

## pa12 (EOS PA 2200)

| Field | Value | URL | Read how |
|---|---|---|---|
| E_xy | 1650 MPa (X, Y, Z all 1650; dry) | https://www.eos.info/polymer-solutions/polymer-materials/data-sheets/mds-pa-2200 | direct (EOS web MDS) |
| nu | 0.3967 (DIC, PA2200 on EOS P395) | Faes et al. 2015 PDF (above) | third-party literature |
| strength_xy | 48 MPa (X and Y, dry) | EOS web MDS | direct |
| strength_z | 42 MPa (Z, dry) | EOS web MDS | direct |
| interlayer_shear | null | - | - |
| density | 0.93 g/cm3 ("EOS Method") | EOS web MDS | direct |
| cost | 75 USD/kg (generic PA12, 10 kg, not EOS) | https://additiveplus.com/product/kspa12-nylon-powder/ | third-party |

## alsi10mg (EOS Aluminium AlSi10Mg)

| Field | Value | URL | Read how |
|---|---|---|---|
| E_xy | 75000 MPa (75 +/- 10 GPa, as built, XY; Z 70 +/- 10; stress-relieved 70 / 60) | 2014 EOS sheet, Wayback copy of gpiprototype.com (above), p.4 | direct text of an EOS document, but hosted by a reseller and archived |
| nu | 0.33 (quoting MatWeb) | https://docs.ntop.com/Product-Documentation/ntop/block-documentation/blocks/design-analysis/sample-materials/al-si-10mg.md | third-party |
| strength_xy | 270 MPa yield Rp0.2, horizontal, as manufactured, M 290 30 um | EOS MDS PDF Wayback copy (above); same numbers on https://www.eos.info/metal-solutions/data-sheets/aluminium/pds-eos-aluminium-alsi10mg-eos-m-290-30um | direct |
| strength_z | 230 MPa yield Rp0.2, vertical, as manufactured | same | direct |
| other conditions (not used) | T6: 250 (V) / 260 (H) yield, 310 / 320 Rm; stress relief: 200 yield, 310 Rm | same | direct |
| interlayer_shear | null | - | - |
| density | >= 2.67 g/cm3 (ISO 3369) | same | direct |
| cost | 41 USD/kg (CNPC powder; Carpenter Additive about 81.50 USD/kg on same site) | https://additiveplus.com/?s=AlSi10Mg&post_type=product | third-party |

## ti64 (EOS Titanium Ti64)

| Field | Value | URL | Read how |
|---|---|---|---|
| E_xy | 110000 MPa (typ. 110 +/- 15 GPa, XY and Z, as built and heat treated) | EOS Ti64 MDS PDF, "400W" sheet 07.2022, p.4 | direct |
| nu | 0.342 (quoting MatWeb) | https://docs.ntop.com/Product-Documentation/ntop/block-documentation/blocks/design-analysis/sample-materials/ti-6al-4v.md | third-party |
| strength_xy | 1000 MPa yield Rp0.2 typ. (+/- 50), heat treated 800 C 4 h argon, XY | EOS Ti64 MDS PDF, p.4 | direct |
| strength_z | 1000 MPa yield typ. (+/- 60), heat treated, Z | EOS Ti64 MDS PDF, p.4 | direct |
| as built (not used) | yield 1140 +/- 50 (XY), 1120 +/- 80 (Z); Rm 1290 / 1240 | EOS Ti64 MDS PDF, p.4 | direct |
| M290 06.2022 sheet (not used) | heat treated 800 C 2 h: yield 945 (H) / 965 (V), Rm 1055 / 1075, density approx. 4.41 | same PDF, first sheet | direct |
| interlayer_shear | null | - | - |
| density | 4.41 g/cm3 | EOS Ti64 MDS PDF, 400W sheet p.3 | direct |
| cost | 136 USD/kg (CNPC Grade 5, 10 kg) | https://additiveplus.com/product/cnpc-ti-6al-4v-grade-5-powder-for-metal-3d-printing-15-53-%c2%b5m-lpbf-10-kg-22-lbs/ | third-party |

## processes

| Process | min wall | URL | Read how |
|---|---|---|---|
| fdm | 0.8 mm (FDM, supported / free) | https://www.hubs.com/knowledge-base/dfm-tips-for-3d-printed-parts-with-thin-walls/ | direct (bureau guide) |
| sls | 0.8 mm for PA12 | https://www.hubs.com/knowledge-base/how-design-parts-sls-3d-printing/ | direct (bureau guide) |
| metal | 0.4 mm DMLS/SLM | https://www.hubs.com/knowledge-base/how-design-parts-metal-3d-printing/ | direct (bureau guide) |
| cross-checks | Protolabs toolkit: PA 12 White 0.762 mm; AlSi10Mg 0.381 / 0.762 mm; Ti-6Al-4V 0.152 / 0.381 mm | https://protolabs.com/resources/design-for-3d-printing-toolkit | direct |
| cross-checks | EOS: AlSi10Mg M 290 30 um min wall 0.4 mm; Ti64 approx. 0.3-0.4 mm | EOS PDFs above | direct |

## Could not source

- Poisson's ratio from any maker TDS/MDS: none of the six sheets lists it. All six nu values are literature or database values and are flagged.
- A measured Poisson's ratio for PETG: only a model-input value (0.4) was found.
- A Poisson's ratio for Fiberon PA6-CF20 itself: used a measured value for Markforged Onyx (short-CF nylon).
- Z-direction strength for Prusament PLA and PETG: the TDS "Vertical xz" column is an on-edge specimen, not Z loading; the "Interlayer Adhesion" row has no defined test method. Z knockdown ratios were taken from Ultimaker TDS data instead.
- Interlayer shear strength: no TDS gives it.
- Young's modulus in the current EOS AlSi10Mg MDS: absent; taken from the 2014 EOS sheet (archived reseller copy).
- An EOS price for PA 2200, AlSi10Mg, or Ti64 powder: none public; reseller prices for non-EOS powders used.
- An FDM minimum-wall figure of about 1.2 mm from a maker or bureau guide: not found; Hubs gives 0.8 mm. Prusa's knowledge base gives no fixed number.
- The live EOS AlSi10Mg MDS PDF: the EOS URL returned 404; a Wayback Machine copy of the same EOS file (2025-07-09) was used. The EOS process-data web page shows the same as-manufactured numbers.
