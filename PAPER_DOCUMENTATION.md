# SmartVision Research Paper & Documentation Package

This package contains the complete, publication-ready research paper and compilation tools for the **Selfie Smart Vision Attendance Portal** final year project.

---

## 📁 Included Documents

1. **`RESEARCH_PAPER.md`**  
   - Complete Markdown research paper formatted for direct reading, markdown-to-pdf conversion, or copy-pasting into formatting software.
   - Includes Abstract, Keywords, Introduction, Literature Survey (20 papers reviewed with taxonomy matrix), System Architecture, Mathematical Formulations, Experimental Results, Comparative Discussions, and 20 IEEE-style References.

2. **`research_paper.tex`**  
   - Official camera-ready IEEE two-column LaTeX source file.
   - Ready for direct import into **[Overleaf](https://www.overleaf.com/)** or local TeX tools (`pdflatex`).

---

## 🎓 Author & Institutional Details Included

- **Paper Title:** *SmartVision: A Scalable Lightweight Multi-Face Biometric Attendance Portal Using ResNet-34 Deep Embeddings and Dynamic Risk Analytics*
- **Authors:** Shivam Vishwakarma [2303031050570], Shivangi Sahu [2303031050571], Nishtha Gupta [2303031050359], Srushti Ghunake [2303031050612]
- **Department:** Computer Science & Engineering, Parul Institute of Engineering & Technology (PIET), Parul University, Vadodara
- **Project Guide:** Prof. Harsh Pateliya, Assistant Professor

---

## 🛠️ How to Compile to PDF

### Method 1: Using Overleaf (Recommended for IEEE Submission)
1. Go to [Overleaf](https://www.overleaf.com/) and log in or create an account.
2. Click **New Project** -> **Blank Project**.
3. Name the project `SmartVision_Research_Paper`.
4. Replace the contents of `main.tex` with the contents of [research_paper.tex](file:///Users/college/Desktop/smartVision_Attendance_Portal/research_paper.tex).
5. Click **Recompile** to generate a two-column IEEE PDF.
6. Download the compiled PDF!

### Method 2: Local TeX Compiler (`pdflatex`)
Run the following command in terminal:
```bash
pdflatex research_paper.tex
bibtex research_paper
pdflatex research_paper.tex
pdflatex research_paper.tex
```

### Method 3: Convert Markdown to PDF via VS Code / Pandoc
If you use Pandoc or VS Code Markdown PDF extension:
```bash
pandoc RESEARCH_PAPER.md -o SmartVision_Research_Paper.pdf --pdf-engine=xelatex
```

---

## 📊 Summary of Literature Review Covered (20 Papers)

| Paper # | Focus / Algorithm | Advantage | Addressed by SmartVision |
|---|---|---|---|
| **1 (2020)** | Viola-Jones & LBP | Real-time face detection | Dlib ResNet-34 overcomes low-light & pose issues |
| **2 (2023)** | CNN & OpenCV | High feature extraction accuracy | Flask CPU server eliminates local GPU requirement |
| **3 (2022)** | MTCNN & FaceNet | Multi-face single frame detection | $\tau=0.50$ threshold & manual override for masks |
| **4 (2019)** | PCA & Eigenfaces | Mathematical feature baseline | 128-D Euclidean vector space projection |
| **5 (2019)** | HOG & SVM | Spatial gradient mapping | Vectorized NumPy matching prevents latency spikes |
| **6 (2021)** | Deep Learning & Haar Cascade | 90%+ recognition rate | Confidence thresholding & distance metrics |
| **7 (2020)** | Django Framework | Web dashboard UI | Flask + SQLAlchemy ORM indexed MySQL queries |
| **8 (2021)** | Mobile & Cloud Storage | Mobile flexibility | Hybrid local/cloud self-hosted deployment |
| **9 (2023)** | 3D Dense Alignment | Robust to 3D rotation | ResNet 68-landmark shape predictor on CPU |
| **10 (2022)** | Hybrid CNN-KNN | Fast classification | Evaluated on diverse illumination & distances |
| **11 (2024)** | LBPH Algorithm | Low-cost small groups | Dynamic re-registration embedding endpoint |
| **12 (2019)** | Haar Cascade & LBPH | Simple GUI | OpenCV contrast enhancement & bilateral filtering |
| **13 (2022)** | Video Stream Processing | Continuous monitoring | Snapshot-based single frame processing (99% bandwidth savings) |
| **14 (2021)** | Biometric Survey | Identifies sector trends | PBKDF2:SHA256 & vector-only BLOB storage (GDPR compliance) |
| **15 (2021)** | LBPH & Excel Export | Basic automated export | High-margin bounding box extraction |
| **16 (2022)** | Haar Cascade Classifier | User-friendly interface | HOG-based face locator precedes CNN encoding |
| **17 (2020)** | HOG Descriptor | Static photo speed | Single JPEG/PNG snapshot ingestion API |
| **18 (2021)** | Biometric CNN | 95% accuracy in lab | Optimized for mid-tier CPU cloud instances (`t3.medium`) |
| **19 (2023)** | LBPH | Anti-proxy focus | Liveness-aware confidence distance metrics |
| **20 (2024)** | SSD & MobileNet | Edge device optimization | Min face size guidelines ($80\times 80$ px) |

---

## 🧮 Key Mathematical Equations in Paper

1. **Triplet Loss Function:**
   $$\mathcal{L}_{triplet} = \sum_{i}^{N} \left[ \| f(\mathbf{I}_i^a) - f(\mathbf{I}_i^p) \|_2^2 - \| f(\mathbf{I}_i^a) - f(\mathbf{I}_i^n) \|_2^2 + \alpha \right]_+$$

2. **128-D Euclidean Distance Metric:**
   $$d(\mathbf{e}_u, \mathbf{e}_s^{(k)}) = \sqrt{\sum_{m=1}^{128} \left( e_{u,m} - e_{s,m}^{(k)} \right)^2}$$

3. **Classification Decision Rule ($\tau = 0.50$):**
   $$C(\mathbf{e}_u) = \arg\min_k d(\mathbf{e}_u, \mathbf{e}_s^{(k)}) \quad \text{if } \min_k d < 0.50$$

4. **Retention Risk State Transition:**
   $$S_{t+1}(k) = \begin{cases} 0 & \text{if Present} \\ S_t(k) + 1 & \text{if Absent} \end{cases} \implies \text{Trigger Alert if } S \ge 5$$
