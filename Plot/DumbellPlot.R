# =============================================================================
# Multi-outcome comparison: Breast / Uterine / Ovarian cancer
# Dumbbell plot — colour = cancer type, size = effect size
# =============================================================================

library(tidyverse)
library(readxl)
library(ggrepel)
library(scales)

# =============================================================================
# 1. Load data
# =============================================================================

read_cancer <- function(path, cancer) {
  raw <- read_excel(path)
  names(raw) <- c(
    "Exposure", "n_studies", "pooled_es_num",
    "ci_low", "ci_high",
    "pi_low", "pi_high",
    "I2", "eggers_p",
    "Total_N", "N_cases"
  )
  raw %>%
    mutate(cancer = cancer,
           sig = ifelse(ci_low > 1 | ci_high < 1, "Significant", "Not significant"))
}

dat_breast    <- read_cancer("C:/Users/mde4023/Downloads/MetaFemina/exposures_meta_analysis_final_combined.xlsx",       "Breast")
dat_uterine   <- read_cancer("C:/Users/mde4023/Downloads/MetaFemina/exposures_meta_analysis_uterine_combined.xlsx",     "Uterine")
dat_ovarian   <- read_cancer("C:/Users/mde4023/Downloads/MetaFemina/exposures_meta_analysis_ovarian_combined.xlsx",     "Ovarian")

dat_all <- bind_rows(dat_breast, dat_uterine, dat_ovarian)

# =============================================================================
# 2. Drop single-study exposures, then keep only those in 2+ cancer datasets
# =============================================================================

shared_exposures <- dat_all %>%
  filter(n_studies > 1) %>%                     # drop single-study exposures first
  distinct(Exposure, cancer) %>%
  count(Exposure) %>%
  filter(n >= 2) %>%
  pull(Exposure)

dat_plot <- dat_all %>%
  filter(Exposure %in% shared_exposures, n_studies > 1)   # apply both filters

# =============================================================================
# 3. Group map & prettify (reuse from forest script)
# =============================================================================

group_map <- tribble(
  ~Exposure,                  ~Group,
  "red_meat",             "Dietary Patterns",
  "fermented_foods",          "Dietary Patterns",
  "skyr",                     "Dietary Patterns",
  "hemp_seeds",               "Fatty Acids & Lipids",
  "kefir",                    "Dietary Patterns",
  "legumes",                  "Fruits & Vegetables",
  "chia_seeds",               "Fatty Acids & Lipids",
  "oats",                     "Dietary Patterns",
  "flax",                     "Phytoestrogens",
  "vitamin_b2",               "B Vitamins",
  "cesium",                   "Minerals & Trace Elements",
  "quercetin",                "Polyphenols & Flavonoids",
  "vitamin_b6",               "B Vitamins",
  "fish_oil",                 "Fatty Acids & Lipids",
  "grape",                    "Fruits & Vegetables",
  "lutein",                   "Carotenoids",
  "molybdenum",               "Minerals & Trace Elements",
  "garlic",                   "Fruits & Vegetables",
  "lycopene",                 "Carotenoids",
  "soy",                      "Phytoestrogens",
  "pantothenic_acid",         "B Vitamins",
  "resveratrol",              "Polyphenols & Flavonoids",
  "vitamin_a",                "Vitamins A, C, D, E",
  "vitamin_b1",               "B Vitamins",
  "mediterranean_diet",       "Dietary Patterns",
  "cod_liver_oil",            "Fatty Acids & Lipids",
  "antioxidants",             "Antioxidants",
  "betaine",                  "Metabolites & Amino Acids",
  "beta-carotene",            "Carotenoids",
  "choline",                  "Metabolites & Amino Acids",
  "magnesium",                "Minerals & Trace Elements",
  "olive",                    "Fruits & Vegetables",
  "vitamin_c",                "Vitamins A, C, D, E",
  "flaxseed",                 "Phytoestrogens",
  "iodine",                   "Minerals & Trace Elements",
  "green_tea",                "Polyphenols & Flavonoids",
  "mushrooms",                "Fruits & Vegetables",
  "calcium",                  "Minerals & Trace Elements",
  "copper",                   "Minerals & Trace Elements",
  "folic_acid",               "B Vitamins",
  "selenium",                 "Minerals & Trace Elements",
  "potassium",                "Minerals & Trace Elements",
  "vitamin_b12",              "B Vitamins",
  "tea",                      "Polyphenols & Flavonoids",
  "mineral_supplements",      "Minerals & Trace Elements",
  "papaya",                   "Fruits & Vegetables",
  "bcaas",                    "Metabolites & Amino Acids",
  "vitamin_e",                "Vitamins A, C, D, E",
  "vitamin_d",                "Vitamins A, C, D, E",
  "omega-3_fatty_acids",      "Fatty Acids & Lipids",
  "caffeine",                 "Dietary Patterns",
  "leucine",                  "Metabolites & Amino Acids",
  "iron",                     "Minerals & Trace Elements",
  "isoleucine",               "Metabolites & Amino Acids",
  "protein_intake",           "Metabolites & Amino Acids",
  "conjugated_linoleic_acid", "Fatty Acids & Lipids",
  "grapefruit",               "Fruits & Vegetables",
  "creatine",                 "Metabolites & Amino Acids",
  "chromium",                 "Minerals & Trace Elements",
  "glutamine",                "Metabolites & Amino Acids",
  "melatonin",                "Hormones & Endogenous",
  "vitamin_k",                "Vitamins A, C, D, E",
  "zinc",                     "Minerals & Trace Elements",
  "carnitine",                "Metabolites & Amino Acids",
  "dehydroepiandrosterone",   "Hormones & Endogenous",
  "cannabidiol",              "Herbal & Botanical",
  "phosphorus",               "Minerals & Trace Elements",
  "ginseng",                  "Herbal & Botanical",
  "vitamin_b3",               "B Vitamins",
  "omega-6_fatty_acids",      "Fatty Acids & Lipids",
  "ginkgo",                   "Herbal & Botanical",
  "coenzyme_q10",             "Antioxidants"
)

group_order <- c(
  "Carotenoids", "Vitamins A, C, D, E", "B Vitamins", "Antioxidants",
  "Minerals & Trace Elements", "Polyphenols & Flavonoids",
  "Fruits & Vegetables", "Fatty Acids & Lipids", "Phytoestrogens",
  "Herbal & Botanical", "Dietary Patterns", "Metabolites & Amino Acids",
  "Hormones & Endogenous"
)

group_colors <- c(
  "B Vitamins"                = "#0057B8",
  "Carotenoids"               = "#E55300",
  "Minerals & Trace Elements" = "#007C7C",
  "Fruits & Vegetables"       = "#2E7D32",
  "Vitamins A, C, D, E"      = "#C79000",
  "Polyphenols & Flavonoids"  = "#6A0DAD",
  "Fatty Acids & Lipids"      = "#B5001F",
  "Phytoestrogens"            = "#7B4A00",
  "Dietary Patterns"          = "#37474F",
  "Herbal & Botanical"        = "#00695C",
  "Metabolites & Amino Acids" = "#880E4F",
  "Hormones & Endogenous"     = "#4527A0",
  "Antioxidants"              = "#1565C0",
  "Other"                     = "#424242"
)

prettify_exposure <- function(x) {
  x %>%
    str_replace_all("_", " ") %>%
    str_to_title() %>%
    str_replace("Bcaas",                   "BCAAs") %>%
    str_replace("Beta-Carotene",           "beta-Carotene") %>%
    str_replace("Omega-3 Fatty Acids",     "Omega-3 FA") %>%
    str_replace("Omega-6 Fatty Acids",     "Omega-6 FA") %>%
    str_replace("Conjugated Linoleic Acid","Conj. LA") %>%
    str_replace("Mineral Supplements",     "Minerals") %>%
    str_replace("Dehydroepiandrosterone",  "DHEA")
}

# =============================================================================
# 4. Prepare final plot data
# =============================================================================

cancer_colors <- c(
  "Breast"  = "#C2185B",
  "Uterine" = "#1565C0",
  "Ovarian" = "#2E7D32"
)

dat_plot <- dat_plot %>%
  left_join(group_map, by = "Exposure") %>%
  mutate(
    Group          = replace_na(Group, "Other"),
    Group          = factor(Group, levels = c(group_order, "Other")),
    Exposure_label = prettify_exposure(Exposure),
    cancer         = factor(cancer, levels = c("Breast", "Uterine", "Ovarian"))
  )

# Order exposures: by group first, then by mean effect size across cancers
exposure_order <- dat_plot %>%
  group_by(Exposure, Exposure_label, Group) %>%
  summarise(mean_es = mean(pooled_es_num, na.rm = TRUE), .groups = "drop") %>%
  arrange(Group, mean_es) %>%
  pull(Exposure_label)

dat_plot <- dat_plot %>%
  mutate(Exposure_label = factor(Exposure_label, levels = exposure_order))

# Dumbbell connectors: min–max range per exposure across cancers
dumbbell_range <- dat_plot %>%
  group_by(Exposure_label, Group) %>%
  summarise(
    es_min = min(pooled_es_num, na.rm = TRUE),
    es_max = max(pooled_es_num, na.rm = TRUE),
    .groups = "drop"
  )

# Group stripe backgrounds
group_stripes <- dat_plot %>%
  distinct(Exposure_label, Group) %>%
  mutate(row_num = as.integer(Exposure_label)) %>%
  group_by(Group) %>%
  summarise(
    y_min = min(row_num) - 0.5,
    y_max = max(row_num) + 0.5,
    .groups = "drop"
  ) %>%
  mutate(fill_col = group_colors[as.character(Group)])

group_bg <- c(
  "B Vitamins"                = "#E3EEFA",
  "Carotenoids"               = "#FDEEE6",
  "Minerals & Trace Elements" = "#DFF2F2",
  "Fruits & Vegetables"       = "#E6F4E6",
  "Vitamins A, C, D, E"      = "#FBF6E0",
  "Polyphenols & Flavonoids"  = "#F2E8FB",
  "Fatty Acids & Lipids"      = "#FBEAED",
  "Phytoestrogens"            = "#F5EDE6",
  "Dietary Patterns"          = "#ECEFF1",
  "Herbal & Botanical"        = "#E0F2EF",
  "Metabolites & Amino Acids" = "#FCE4EF",
  "Hormones & Endogenous"     = "#EDE7F6",
  "Antioxidants"              = "#E3EEF9",
  "Other"                     = "#F5F5F5"
)

# =============================================================================
# 5. Build plot
# =============================================================================

p <- ggplot() +
  # Group background stripes
  geom_rect(
    data = group_stripes,
    aes(xmin = -Inf, xmax = Inf, ymin = y_min, ymax = y_max, fill = Group),
    alpha = 0.35, inherit.aes = FALSE
  ) +
  scale_fill_manual(values = group_bg, guide = "none") +
  # Null line
  geom_vline(xintercept = 1, linetype = "dashed", linewidth = 0.6, color = "#455A64") +
  # Dumbbell connector (min to max ES across cancers)
  geom_segment(
    data = dumbbell_range,
    aes(x = es_min, xend = es_max,
        y = Exposure_label, yend = Exposure_label),
    color = "#B0BEC5", linewidth = 1.0, lineend = "round"
  ) +
  # CI whiskers per cancer type
  geom_segment(
    data = dat_plot,
    aes(x = ci_low, xend = ci_high,
        y = Exposure_label, yend = Exposure_label,
        color = cancer),
    linewidth = 0.45, alpha = 0.5, lineend = "round"
  ) +
  # Main dots
  geom_point(
    data = dat_plot,
    aes(x = pooled_es_num, y = Exposure_label,
        color = cancer, size = n_studies,         # <-- now driven by n_studies
        shape = sig),
    alpha = 0.92
  ) +
  # Per-exposure group label on right margin
  geom_text(
    data = dat_plot %>%
      distinct(Exposure_label, Group),
    aes(x = Inf, y = Exposure_label,
        label = as.character(Group),
        color = Group),
    hjust = -0.05, size = 4.1, fontface = "italic",    # was 2.8
    inherit.aes = FALSE
  ) +
  scale_color_manual(
    values = c(cancer_colors, group_colors),
    breaks = names(cancer_colors),   # only show cancer types in legend
    name   = "Cancer type"
  ) +
  scale_size_continuous(
    range  = c(2, 7),
    name   = "Number of studies (k)",             # <-- was "Pooled RR (size)"
    guide  = guide_legend(override.aes = list(shape = 16, color = "grey40"))
  ) +
  scale_shape_manual(
    values = c("Significant" = 16, "Not significant" = 1),
    name   = "Significance"
  ) +
  scale_x_log10(
    breaks = c(0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4),
    labels = c("0.25", "0.5", "0.75", "1", "1.5", "2", "3", "4")
  ) +
  coord_cartesian(clip = "off") +
  labs(
    title    = "Comparison of exposure effects across gynaecological cancers",
    subtitle = "Exposures present in ≥2 cancer datasets  |  filled circle = significant (95% CI excludes 1.0)",
    x        = "Pooled RR (log scale)",
    y        = NULL
  ) +
  theme_minimal(base_size = 16) +   # was 11
  theme(
    plot.title         = element_text(face = "bold", size = 20, color = "#1A1A2E"),
    plot.subtitle      = element_text(size = 13, color = "#607D8B"),
    axis.text.y        = element_text(size = 13, color = "#1A1A2E"),
    axis.text.x        = element_text(size = 13, color = "#37474F", face = "bold"),
    axis.title.x       = element_text(size = 14, color = "#37474F", margin = margin(t = 6)),
    panel.grid.major.y = element_blank(),
    panel.grid.major.x = element_line(color = "#ECEFF1", linewidth = 0.4),
    panel.grid.minor   = element_blank(),
    legend.position    = "bottom",
    legend.box         = "horizontal",
    legend.text        = element_text(size = 13),
    legend.title       = element_text(size = 14, face = "bold"),
    plot.margin        = margin(10, 160, 10, 10),
    plot.background    = element_rect(fill = "white", color = NA)
  )

# =============================================================================
# 6. Save
# =============================================================================

ggsave(
  "comparison_dumbbell.pdf",
  plot   = p,
  width  = 430,      # was 320
  height = 380,      # was 300
  units  = "mm",
  device = "pdf",
  dpi    = 300
)

message("Saved: comparison_dumbbell.pdf")