# =============================================================================
# Combined analysis plots — Forest plots + Scatter diagnostic plots
# Data: exposures_meta_analysis_final_combined.xlsx
# =============================================================================

library(tidyverse)
library(scales)
library(readxl)
library(stringr)
library(cowplot)
library(ggtext)
library(ggrepel)
library(patchwork)

for (pkg in c("ggtext", "cowplot", "ggrepel", "patchwork")) {
  if (!requireNamespace(pkg, quietly = TRUE)) install.packages(pkg)
}

# =============================================================================
# 1. Read & clean data
# =============================================================================

raw <- read_excel("C:/Users/mde4023/Downloads/MetaFemina/exposures_meta_analysis_final_combined.xlsx")

# Standardise column names
names(raw) <- c(
  "Exposure", "n_studies", "pooled_es_num",
  "ci_low", "ci_high",
  "pi_low", "pi_high",
  "I2", "eggers_p",
  "Total_N", "N_cases"
)

dat_clean <- raw %>%
  mutate(
    # Reconstruct a display string  "OR (low–high)" for the table column
    pooled_ci_lab = paste0(
      pooled_es_num,
      " (", ci_low, "-", ci_high, ")"
    ),
    N_lab     = comma(Total_N),
    Cases_lab = comma(N_cases),
    sig = ifelse((ci_high < 1 | ci_low > 1), "Significant", "Not significant"),
    direction = case_when(
      pooled_es_num < 1 ~ "Protective",
      pooled_es_num > 1 ~ "Harmful",
      TRUE              ~ "Neutral"
    )
  )

# =============================================================================
# 2. Group mapping, order & colour palettes  (unchanged from original)
# =============================================================================

group_map <- tribble(
  ~Exposure,                  ~Group,
  "eggs",                     "Dietary Patterns",
  "dairy",                    "Dietary Patterns",
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
  "Carotenoids",
  "Vitamins A, C, D, E",
  "B Vitamins",
  "Antioxidants",
  "Minerals & Trace Elements",
  "Polyphenols & Flavonoids",
  "Fruits & Vegetables",
  "Fatty Acids & Lipids",
  "Phytoestrogens",
  "Herbal & Botanical",
  "Dietary Patterns",
  "Metabolites & Amino Acids",
  "Hormones & Endogenous"
)

group_colors <- c(
  "B Vitamins"               = "#0057B8",
  "Carotenoids"              = "#E55300",
  "Minerals & Trace Elements"= "#007C7C",
  "Fruits & Vegetables"      = "#2E7D32",
  "Vitamins A, C, D, E"     = "#C79000",
  "Polyphenols & Flavonoids" = "#6A0DAD",
  "Fatty Acids & Lipids"     = "#B5001F",
  "Phytoestrogens"           = "#7B4A00",
  "Dietary Patterns"         = "#37474F",
  "Herbal & Botanical"       = "#00695C",
  "Metabolites & Amino Acids"= "#880E4F",
  "Hormones & Endogenous"    = "#4527A0",
  "Antioxidants"             = "#1565C0",
  "Other"                    = "#424242"
)

group_bg <- c(
  "B Vitamins"               = "#E3EEFA",
  "Carotenoids"              = "#FDEEE6",
  "Minerals & Trace Elements"= "#DFF2F2",
  "Fruits & Vegetables"      = "#E6F4E6",
  "Vitamins A, C, D, E"     = "#FBF6E0",
  "Polyphenols & Flavonoids" = "#F2E8FB",
  "Fatty Acids & Lipids"     = "#FBEAED",
  "Phytoestrogens"           = "#F5EDE6",
  "Dietary Patterns"         = "#ECEFF1",
  "Herbal & Botanical"       = "#E0F2EF",
  "Metabolites & Amino Acids"= "#FCE4EF",
  "Hormones & Endogenous"    = "#EDE7F6",
  "Antioxidants"             = "#E3EEF9",
  "Other"                    = "#F5F5F5"
)

# =============================================================================
# 3. Helper: pretty exposure labels
# =============================================================================

prettify_exposure <- function(x) {
  x %>%
    str_replace_all("_", " ") %>%
    str_to_title() %>%
    str_replace("Bcaas",                   "BCAAs") %>%
    str_replace("Beta-Carotene",            "beta-Carotene") %>%
    str_replace("Omega-3 Fatty Acids",      "Omega-3 FA") %>%
    str_replace("Omega-6 Fatty Acids",      "Omega-6 FA") %>%
    str_replace("Conjugated Linoleic Acid", "Conj. LA") %>%
    str_replace("Mineral Supplements",      "Minerals") %>%
    str_replace("Dehydroepiandrosterone",   "DHEA")
}

# =============================================================================
# 4. Forest plot helpers  (identical logic to original)
# =============================================================================

prepare_dat <- function(dat_clean, dir) {
  dat_clean %>%
    filter(n_studies > 1) %>%
    left_join(group_map, by = "Exposure") %>%
    mutate(
      Group          = replace_na(Group, "Other"),
      Exposure_label = prettify_exposure(Exposure),
      Group          = factor(Group, levels = c(group_order, "Other"))
    ) %>%
    filter(direction == dir) %>%
    arrange(Group, pooled_es_num) %>%
    mutate(row = row_number())
}

build_plot_rows <- function(df) {
  groups_present <- df %>%
    group_by(Group) %>%
    summarise(n = n(), .groups = "drop") %>%
    arrange(match(Group, c(group_order, "Other")))
  
  plot_row   <- integer(nrow(df))
  label_rows <- list()
  current_row <- 1
  
  for (i in seq_len(nrow(groups_present))) {
    grp   <- as.character(groups_present$Group[i])
    n_grp <- groups_present$n[i]
    
    label_rows[[i]] <- tibble(plot_row = current_row, Group = grp, is_label = TRUE)
    current_row <- current_row + 1
    
    idx <- which(as.character(df$Group) == grp)
    plot_row[idx] <- seq(current_row, current_row + n_grp - 1)
    current_row <- current_row + n_grp
  }
  
  df$plot_row <- plot_row
  list(df = df, labels = bind_rows(label_rows), total_rows = current_row - 1)
}

# ---- Table panel ----
make_table_panel <- function(df, label_df, total_rows, title_text, fs = 3.8) {
  header_y <- 0
  y_lim    <- c(total_rows + 0.6, -0.65)
  
  ggplot() +
    geom_rect(data = df,
              aes(ymin = plot_row - 0.5, ymax = plot_row + 0.5,
                  xmin = -0.05, xmax = 4.75, fill = as.character(Group)),
              alpha = 0.30, inherit.aes = FALSE) +
    scale_fill_manual(values = group_bg, guide = "none") +
    geom_hline(yintercept = seq(0.5, total_rows + 0.5, 1),
               color = "white", linewidth = 0.6) +
    geom_rect(data = label_df,
              aes(ymin = plot_row - 0.5, ymax = plot_row + 0.5,
                  xmin = -0.05, xmax = 4.75, fill = Group),
              alpha = 0.70, inherit.aes = FALSE) +
    geom_text(data = label_df,
              aes(x = 0.0, y = plot_row, label = toupper(Group), color = Group),
              hjust = 0, size = fs - 0.3, fontface = "bold.italic", inherit.aes = FALSE) +
    scale_color_manual(values = group_colors, guide = "none") +
    geom_text(data = df,
              aes(x = 0.15, y = plot_row, label = Exposure_label,
                  color = as.character(Group)),
              hjust = 0, size = fs, fontface = "bold", inherit.aes = FALSE) +
    geom_text(data = df,
              aes(x = 1.2, y = plot_row, label = as.character(n_studies),
                  color = as.character(Group)),
              hjust = 0.5, size = fs - 0.2, inherit.aes = FALSE) +
    geom_text(data = df,
              aes(x = 2.4, y = plot_row, label = N_lab,
                  color = as.character(Group)),
              hjust = 1, size = fs - 0.2, inherit.aes = FALSE) +
    geom_text(data = df,
              aes(x = 3.5, y = plot_row, label = Cases_lab,
                  color = as.character(Group)),
              hjust = 1, size = fs - 0.2, inherit.aes = FALSE) +
    geom_text(data = df,
              aes(x = 4.7, y = plot_row, label = pooled_ci_lab,
                  color = as.character(Group)),
              hjust = 1, size = fs - 0.2, fontface = "italic", inherit.aes = FALSE) +
    annotate("rect",
             xmin = -0.05, xmax = 4.75, ymin = -0.60, ymax = 0.50,
             fill = "#1A1A2E", alpha = 0.93) +
    annotate("text", x = 0.0, y = header_y, label = "Exposure",
             hjust = 0, fontface = "bold", size = fs + 0.5, color = "white") +
    annotate("text", x = 1.2, y = header_y, label = "N studies",
             hjust = 0.5, fontface = "bold", size = fs + 0.5, color = "white") +
    annotate("text", x = 2.4, y = header_y, label = "N",
             hjust = 1, fontface = "bold", size = fs + 0.5, color = "white") +
    annotate("text", x = 3.5, y = header_y, label = "Cases",
             hjust = 1, fontface = "bold", size = fs + 0.5, color = "white") +
    annotate("text", x = 4.7, y = header_y, label = "Pooled RR (95% CI)",
             hjust = 1, fontface = "bold", size = fs + 0.5, color = "white") +
    scale_x_continuous(limits = c(-0.05, 4.8), expand = c(0, 0)) +
    scale_y_continuous(limits = y_lim, trans = "reverse", expand = c(0, 0)) +
    labs(title = title_text) +
    theme_void() +
    theme(
      plot.title      = element_text(face = "bold", hjust = 0.5, size = 13,
                                     color = "#1A1A2E", margin = margin(b = 8, t = 4)),
      plot.background = element_rect(fill = "white", color = NA),
      plot.margin     = margin(8, 4, 8, 10)
    )
}

# ---- Forest panel ----
make_forest_panel <- function(df, label_df, total_rows, xlim_max = 2.5, fs = 3.8) {
  header_y <- 0
  y_lim    <- c(total_rows + 0.6, -0.65)
  # Forest panel x-axis settings
  xlim_min <- 0.15
  x_breaks_all <- c(0.2, 0.25, 0.5, 1, 2, 4)
  x_breaks <- x_breaks_all[x_breaks_all >= xlim_min & x_breaks_all <= xlim_max]
  ggplot() +
    geom_rect(data = df,
              aes(ymin = plot_row - 0.5, ymax = plot_row + 0.5,
                  xmin = xlim_min, xmax = xlim_max, fill = as.character(Group)),
              alpha = 0.28, inherit.aes = FALSE) +
    scale_fill_manual(values = group_bg, guide = "none") +
    geom_hline(yintercept = seq(0.5, total_rows + 0.5, 1),
               color = "white", linewidth = 0.6) +
    geom_rect(data = label_df,
              aes(ymin = plot_row - 0.5, ymax = plot_row + 0.5,
                  xmin = xlim_min, xmax = xlim_max, fill = Group),
              alpha = 0.65, inherit.aes = FALSE) +
    geom_vline(xintercept = x_breaks[x_breaks != 1],
               color = "grey78", linewidth = 0.3, linetype = "dotted") +
    geom_vline(xintercept = 1,
               linetype = "dashed", linewidth = 0.7, color = "#1A1A2E") +
    # CI whiskers
    # CI whisker (main horizontal line)
    geom_segment(data = df,
                 aes(x    = pmax(ci_low,  xlim_min),
                     xend = pmin(ci_high, xlim_max),
                     y = plot_row, yend = plot_row,
                     color = as.character(Group)),
                 linewidth = 1.1, lineend = "round", inherit.aes = FALSE) +
    
    # Left end-cap tick — only draw if ci_low is within range
    geom_segment(data = df %>% filter(ci_low >= xlim_min),
                 aes(x = ci_low, xend = ci_low,
                     y = plot_row - 0.18, yend = plot_row + 0.18,
                     color = as.character(Group)),
                 linewidth = 0.7, inherit.aes = FALSE) +
    
    # Right end-cap tick — only draw if ci_high is within range
    geom_segment(data = df %>% filter(ci_high <= xlim_max),
                 aes(x = ci_high, xend = ci_high,
                     y = plot_row - 0.18, yend = plot_row + 0.18,
                     color = as.character(Group)),
                 linewidth = 0.7, inherit.aes = FALSE) +
    # Prediction interval whiskers (dashed, thinner) — only where available
    geom_segment(data = df %>% filter(!is.na(pi_low) & !is.na(pi_high)),
                 aes(x = pmax(pi_low, xlim_min), xend = pmin(pi_high, xlim_max),
                     y = plot_row, yend = plot_row,
                     color = as.character(Group)),
                 linewidth = 0.45, linetype = "dashed",
                 lineend = "round", inherit.aes = FALSE) +
    # Non-significant diamonds
    geom_point(data = df %>% filter(sig == "Not significant"),
               aes(x = pooled_es_num, y = plot_row,
                   color = as.character(Group), size = n_studies),
               shape = 18, alpha = 0.38, inherit.aes = FALSE) +
    # Significant: white halo + coloured diamond + red outline
    geom_point(data = df %>% filter(sig == "Significant"),
               aes(x = pooled_es_num, y = plot_row, size = n_studies * 1.9),
               shape = 18, color = "white", alpha = 0.55, inherit.aes = FALSE) +
    geom_point(data = df %>% filter(sig == "Significant"),
               aes(x = pooled_es_num, y = plot_row,
                   color = as.character(Group), size = n_studies),
               shape = 18, alpha = 1.0, inherit.aes = FALSE) +
    geom_point(data = df %>% filter(sig == "Significant"),
               aes(x = pooled_es_num, y = plot_row, size = n_studies * 0.9),
               shape = 5, color = "#CC0000", stroke = 1.1, alpha = 0.95,
               inherit.aes = FALSE) +
    # Header bar
    annotate("rect",
             xmin = xlim_min, xmax = xlim_max, ymin = -0.60, ymax = 0.50,
             fill = "#1A1A2E", alpha = 0.93) +
    annotate("text", x = 1, y = header_y, label = "Effect size", hjust = 0.5,
             fontface = "bold", size = fs + 0.5, color = "white") +
    scale_x_log10(
      limits = c(xlim_min, xlim_max),
      breaks = x_breaks,
      labels = as.character(x_breaks),
      expand = c(0, 0)
    )+
    scale_y_continuous(limits = y_lim, trans = "reverse", expand = c(0, 0)) +
    scale_color_manual(
      values = group_colors,
      name   = "Exposure group",
      guide  = guide_legend(
        ncol           = 4,
        override.aes   = list(shape = 15, size = 5.5, alpha = 1),
        title.position = "top",
        title.hjust    = 0,
        byrow          = TRUE
      )
    ) +
    scale_size_continuous(range = c(2.0, 6.5), guide = "none") +
    labs(x = "Pooled RR (log scale)", y = NULL) +
    theme_minimal(base_size = 11) +
    theme(
      axis.text.y      = element_blank(),
      axis.ticks.y     = element_blank(),
      axis.text.x      = element_text(size = 10, color = "#37474F", face = "bold"),
      axis.title.x     = element_text(size = 11, color = "#37474F", margin = margin(t = 6)),
      panel.grid       = element_blank(),
      legend.position  = "bottom",
      legend.text      = element_text(size = 9,  color = "#1A1A2E"),
      legend.title     = element_text(size = 10, color = "#1A1A2E", face = "bold"),
      legend.key.size  = unit(0.55, "cm"),
      legend.spacing.x = unit(0.4, "cm"),
      plot.background  = element_rect(fill = "white", color = NA),
      plot.margin      = margin(8, 16, 8, 2)
    )
}

# ---- Caption ----
make_caption <- function(direction) {
  side <- if (direction == "Protective") {
    "RR < 1 = inversely associated with breast cancer risk."
  } else {
    "RR > 1 = positively associated with breast cancer risk."
  }
  paste0(
    "[*] pooled RR (size proportional to k studies)  |  ",
    "[ ] red outline = statistically significant (95% CI excludes 1.0)  |  ",
    "[*] faded = non-significant  |  dashed line = 95% prediction interval  |  "
  )
}

# ---- Compose & save ----
save_forest_figure <- function(direction, title_text, xlim_max, filename) {
  df_raw     <- prepare_dat(dat_clean, direction)
  built      <- build_plot_rows(df_raw)
  df         <- built$df
  label_df   <- built$labels
  total_rows <- built$total_rows
  
  tbl        <- make_table_panel(df, label_df, total_rows, title_text)
  fst        <- make_forest_panel(df, label_df, total_rows, xlim_max)
  legend_grob <- get_legend(fst)
  fst_no_leg  <- fst + theme(legend.position = "none")
  
  caption_grob <- ggdraw() +
    draw_label(make_caption(direction),
               x = 0.01, hjust = 0, size = 7.5,
               color = "#607D8B", fontface = "italic")
  
  combined <- plot_grid(
    plot_grid(tbl, fst_no_leg,
              ncol = 2, rel_widths = c(1.55, 1),
              align = "h", axis = "tb"),
    legend_grob,
    caption_grob,
    ncol        = 1,
    rel_heights = c(1, 0.09, 0.06)
  )
  
  final <- ggdraw(combined) +
    draw_line(x = c(0, 1, 1, 0, 0),
              y = c(0, 0, 1, 1, 0),
              color = "#B0BEC5", linewidth = 0.8)
  
  ggsave(filename,
         plot = final, width = 297, height = 250,
         units = "mm", device = "pdf", dpi = 300)
  message("Saved: ", filename)
  invisible(final)
}

# =============================================================================
# 5. Scatter / diagnostic plots  (Plot.R style, adapted for new columns)
#    Two separate functions — one per plot
# =============================================================================

# Shared helper: build the filtered + labelled data frame
build_scatter_df <- function(dat_clean, min_studies = 2) {
  dat_clean %>%
    filter(n_studies > min_studies) %>%
    left_join(group_map, by = "Exposure") %>%
    mutate(
      Group          = replace_na(Group, "Other"),
      Group          = factor(Group, levels = c(group_order, "Other")),
      exposure_label = prettify_exposure(Exposure),
      log_eggers_p   = log(eggers_p)   # natural log, same as original
    )
}

# ---- Plot 1: Effect Size vs I² ----
make_es_heterogeneity_plot <- function(dat_clean, min_studies = 2,
                                       filename = "plot_es_vs_heterogeneity.pdf") {
  
  plot_df <- build_scatter_df(dat_clean, min_studies)
  
  p <- ggplot(plot_df,
              aes(x = pooled_es_num, y = I2, color = as.character(Group))) +
    geom_point(aes(size = n_studies), alpha = 0.85) +
    geom_text_repel(aes(label = exposure_label), size = 3, max.overlaps = 20) +
    geom_vline(xintercept = 1, linetype = "dashed") +
    scale_color_manual(values = group_colors, guide = "none") +
    scale_size_continuous(range = c(1, 4), name = "Number of studies") +
    labs(
      title = "Effect Size vs Heterogeneity",
      x     = "Effect Size (Pooled RR)",
      y     = expression(I^2)
    ) +
    theme_minimal(base_size = 15) +
    theme(
      legend.position = "none",
      plot.title      = element_text(face = "bold")
    )
  
  ggsave(filename,
         plot = p, width = 210, height = 210,
         units = "mm", device = "pdf", dpi = 300)
  message("Saved: ", filename)
  invisible(p)
}

# ---- Plot 2: log(Egger's p-value) vs I² ----
make_eggers_heterogeneity_plot <- function(dat_clean, min_studies = 2,
                                           filename = "plot_eggers_vs_heterogeneity.pdf") {
  
  plot_df <- build_scatter_df(dat_clean, min_studies) %>%
    filter(!is.na(log_eggers_p))
  
  p <- ggplot(plot_df,
              aes(x = log_eggers_p, y = I2, color = as.character(Group))) +
    geom_point(aes(size = n_studies), alpha = 0.85) +
    geom_text_repel(aes(label = exposure_label), size = 3, max.overlaps = 20) +
    geom_vline(xintercept = log(0.05), linetype = "dashed") +   # log(0.05) ≈ -2.996
    scale_color_manual(values = group_colors, guide = "none") +
    scale_size_continuous(range = c(1, 4), name = "Number of studies") +
    labs(
      title = "Egger's Test log(p-value) vs Heterogeneity",
      x     = "log(Egger's p-value)",
      y     = expression(I^2)
    ) +
    theme_minimal(base_size = 15) +
    theme(
      legend.position = "none",
      plot.title      = element_text(face = "bold")
    )
  
  ggsave(filename,
         plot = p, width = 210, height = 210,
         units = "mm", device = "pdf", dpi = 300)
  message("Saved: ", filename)
  invisible(p)
}

# =============================================================================
# 6. Render all figures
# =============================================================================

save_forest_figure(
  direction  = "Protective",
  title_text = "Exposures inversely associated with breast cancer risk\n(meta-analysis of observational studies)",
  xlim_max   = 2.2,
  filename   = "forest_protective.pdf"
)

save_forest_figure(
  direction  = "Harmful",
  title_text = "Exposures positively associated with breast cancer risk\n(meta-analysis of observational studies)",
  xlim_max   = 4.5,
  filename   = "forest_harmful.pdf"
)

make_es_heterogeneity_plot(
  dat_clean   = dat_clean,
  min_studies = 2,
  filename    = "plot_es_vs_heterogeneity.pdf"
)

make_eggers_heterogeneity_plot(
  dat_clean   = dat_clean,
  min_studies = 2,
  filename    = "plot_eggers_vs_heterogeneity.pdf"
)

message("All figures saved.")


