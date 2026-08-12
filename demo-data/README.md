# ReconAI Demo Dataset & Mock Documents

Folder ini berisi kumpulan dataset sampel dokumen invoice/kuitansi dan mutasi bank CSV untuk pengujian end-to-end (E2E) dan demonstrasi fitur **ReconAI Agent Platform**.

---

## 📁 Struktur Dataset

```
demo-data/
├── bank_statements/
│   └── mock_bank_statement_august_2026.csv   # Mutasi bank CSV untuk tes rekonsiliasi
├── invoices/
│   ├── invoice_01_aws_cloud.pdf              # Subscription Server Cloud (AWS)
│   ├── invoice_02_office_supplies.pdf        # Pembelian ATK Kantor
│   ├── invoice_03_tokopedia_equipment.pdf    # Pembelian Peralatan IT Kantor
│   ├── invoice_04_pln_electricity.pdf        # Tagihan Listrik PLN Kantor
│   ├── invoice_05_starbucks_meeting.pdf      # Jamuan Klien / Meeting Expense
│   └── invoice_06_blurry_low_confidence.pdf  # Dokumen kualitas rendah (Low Confidence Test)
└── README.md                                 # Dokumentasi dataset ini
```

---

## 🧪 Skenario Pengujian

1. **Happy Path (OCR -> Auto-Bookkeeping -> Post):**
   - Upload `invoice_01_aws_cloud.pdf` atau `invoice_03_tokopedia_equipment.pdf`.
   - AI Agent akan mengekstrak vendor, tanggal, total, dan menyarankan entri jurnal seimbang.
2. **Review Queue (Sensitive Account / Low Confidence):**
   - Upload `invoice_06_blurry_low_confidence.pdf`.
   - Skor keyakinan OCR < 0.85 sehingga secara otomatis masuk ke **Human Review Queue**.
3. **Bank Statement Reconciliation:**
   - Masuk ke tab **Bank Reconciliation**, impor file `mock_bank_statement_august_2026.csv`.
   - Jalankan **Recon Engine** untuk mencocokkan transaksi mutasi bank secara otodidak dengan entri jurnal yang telah diposting.
