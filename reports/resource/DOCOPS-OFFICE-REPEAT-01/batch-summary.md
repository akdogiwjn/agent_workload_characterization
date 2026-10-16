# DOCOPS Office Repeat 01 批次结果

Identity SHA-256：`25da9eeab2600401630ca54aa11f739dbfe08be3a57d6d4808fbc8956d65712a`

| Round | Task | Run | 状态 | 请求 | 工具类别计数 | 终止 | Reward | Wall s | CPU core-s | memory.current 峰值 B |
|---:|---|---|---|---:|---|---|---:|---:|---:|---:|
| 0 | excel_001_budget_bucket_totals_seed | 20261010T154928Z-r0-excel001 | executed | 7 | {"file_copy": 1, "spreadsheet_formula_edit": 1, "spreadsheet_inspection": 1} | finish | 1.0 | 50.3 | 7.069852 | 67645440 |
| 0 | ppt_008_bullet_editing_seed | 20261010T155019Z-r0-ppt008 | executed | 5 | {"presentation_inspection": 2, "file_copy": 1, "presentation_text_edit": 1} | finish | 1.0 | 25.43 | 5.366808 | 85241856 |
| 0 | pdf_004_audit_pages_reorder_seed | 20261010T155045Z-r0-pdf004 | executed | 4 | {"file_copy": 1, "pdf_page_reorder": 1, "document_structure_inspection": 1} | finish | 1.0 | 21.55 | 4.014582 | 62980096 |
| 1 | ppt_008_bullet_editing_seed | 20261010T155107Z-r1-ppt008 | executed | 6 | {"file_copy": 1, "presentation_inspection": 2, "presentation_text_edit": 1} | finish | 1.0 | 25.2 | 5.209944 | 63598592 |
| 1 | pdf_004_audit_pages_reorder_seed | 20261010T155132Z-r1-pdf004 | executed | 4 | {"file_copy": 1, "pdf_page_reorder": 1, "document_structure_inspection": 1} | finish | 1.0 | 21.73 | 4.31821 | 58531840 |
| 1 | excel_001_budget_bucket_totals_seed | 20261010T155154Z-r1-excel001 | executed | 6 | {"spreadsheet_inspection": 2, "file_copy": 1, "spreadsheet_formula_edit": 2} | finish | 1.0 | 32.34 | 6.006818 | 78770176 |
| 2 | pdf_004_audit_pages_reorder_seed | 20261010T155227Z-r2-pdf004 | executed | 4 | {"file_copy": 1, "pdf_page_reorder": 1, "document_structure_inspection": 1} | finish | 1.0 | 20.81 | 4.279262 | 66600960 |
| 2 | excel_001_budget_bucket_totals_seed | 20261010T155248Z-r2-excel001 | executed | 8 | {"file_copy": 1, "spreadsheet_inspection": 2, "spreadsheet_formula_edit": 2} | finish | 1.0 | 34.47 | 5.969424 | 76169216 |
| 2 | ppt_008_bullet_editing_seed | 20261010T155323Z-r2-ppt008 | executed | 5 | {"presentation_inspection": 2, "file_copy": 1, "presentation_text_edit": 1} | finish | 1.0 | 24.74 | 4.932665 | 71151616 |

停止原因：无。
状态 `executed` 表示 attempt 链与归档完成，不表示 reward 成功。
容器资源为共享任务容器观测，不归因到单个工具；请求数是已保存逻辑请求日志，未必覆盖底层重试。
