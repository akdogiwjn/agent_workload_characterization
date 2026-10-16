# DOCOPS-OFFICE-REPEAT-02 批次结果

Identity SHA-256：`0886c0b0d64ae20813f518e0c0392d370d98f5a8479737bccabdd5016c539bf1`

| Round | Task | Run | 状态 | 请求 | 工具类别计数 | 终止 | Reward | Wall s | CPU core-s | memory.current 峰值 B |
|---:|---|---|---|---:|---|---|---:|---:|---:|---:|
| 0 | excel_001_budget_bucket_totals_seed | 20261011T104235Z-r0-excel001 | executed | 7 | {"file_copy": 1, "spreadsheet_inspection": 3, "spreadsheet_formula_edit": 2} | finish | 1.0 | 42.97 | 6.840446 | 82657280 |
| 0 | ppt_008_bullet_editing_seed | 20261011T104318Z-r0-ppt008 | executed | 5 | {"file_copy": 1, "presentation_inspection": 2, "presentation_text_edit": 1} | finish | 1.0 | 25.27 | 5.368005 | 61702144 |
| 0 | pdf_004_audit_pages_reorder_seed | 20261011T104344Z-r0-pdf004 | executed | 4 | {"file_copy": 1, "pdf_page_reorder": 1, "document_structure_inspection": 1} | finish | 1.0 | 21.5 | 4.270158 | 76206080 |
| 1 | ppt_008_bullet_editing_seed | 20261011T104406Z-r1-ppt008 | executed | 5 | {"file_copy": 1, "presentation_inspection": 2, "presentation_text_edit": 1} | finish | 1.0 | 24.64 | 5.034718 | 71262208 |
| 1 | pdf_004_audit_pages_reorder_seed | 20261011T104431Z-r1-pdf004 | executed | 4 | {"file_copy": 1, "pdf_page_reorder": 1, "document_structure_inspection": 1} | finish | 1.0 | 22.05 | 4.518449 | 82034688 |
| 1 | excel_001_budget_bucket_totals_seed | 20261011T104454Z-r1-excel001 | executed | 6 | {"spreadsheet_inspection": 2, "file_copy": 1, "spreadsheet_formula_edit": 2} | finish | 1.0 | 49.05 | 6.053172 | 70393856 |
| 2 | pdf_004_audit_pages_reorder_seed | 20261011T104543Z-r2-pdf004 | executed | 4 | {"file_copy": 1, "pdf_page_reorder": 1, "document_structure_inspection": 1} | finish | 1.0 | 21.16 | 4.461739 | 67649536 |
| 2 | excel_001_budget_bucket_totals_seed | 20261011T104605Z-r2-excel001 | executed | 6 | {"spreadsheet_inspection": 2, "file_copy": 1, "spreadsheet_formula_edit": 2} | finish | 1.0 | 35.95 | 6.733122 | 86966272 |
| 2 | ppt_008_bullet_editing_seed | 20261011T104641Z-r2-ppt008 | executed | 5 | {"file_copy": 1, "presentation_inspection": 2, "presentation_text_edit": 1} | finish | 1.0 | 25.88 | 5.557092 | 68624384 |

停止原因：无。
状态 `executed` 表示 attempt 链与归档完成，不表示 reward 成功。
容器资源为共享任务容器观测，不归因到单个工具；请求数是已保存逻辑请求日志，未必覆盖底层重试。
