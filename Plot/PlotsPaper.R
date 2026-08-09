# =============================================================================
# Cancer-specific forest plots and diagnostic plots
# Data: combined and dietary-only meta-analysis workbooks
# =============================================================================
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(script_arg) == 1) {
  setwd(dirname(normalizePath(sub("^--file=", "", script_arg))))
}
library(tidyverse)
library(scales)
library(readxl)
library(stringr)
library(cowplot)
library(ggtext)
library(ggrepel)
library(patchwork)

for (pkg in c("ggtext", "cowplot", "ggrepel", "patchwork", "jsonlite")) {
  if (!requireNamespace(pkg, quietly = TRUE)) install.packages(pkg)
}

output_dir <- "."
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)
analysis_json_path <- Sys.getenv("METAFEMINA_ANALYSIS_JSON", "")
analysis_json <- if (nzchar(analysis_json_path)) jsonlite::fromJSON(analysis_json_path) else NULL

summary_plot_locales <- c("zh-CN", "zh-TW", "nl", "ko")
translation_catalog_path <- file.path("..", "static", "i18n-translations.json")
if (!file.exists(translation_catalog_path)) {
  stop("Required translation catalog is missing: ", translation_catalog_path)
}
translation_catalog <- jsonlite::fromJSON(
  translation_catalog_path,
  simplifyVector = FALSE
)

normalize_translation_key <- function(x) {
  x %>%
    as.character() %>%
    str_to_lower() %>%
    str_replace_all("[^a-z0-9]+", "_") %>%
    str_replace_all("^_+|_+$", "")
}

translation_source_by_key <- setNames(
  names(translation_catalog),
  normalize_translation_key(names(translation_catalog))
)

localized_group_labels <- list(
  "zh-CN" = c(
    "Carotenoids" = "类胡萝卜素",
    "Vitamins A, C, D, E, K" = "维生素 A、C、D、E、K",
    "B Vitamins" = "B族维生素",
    "Antioxidants" = "抗氧化剂",
    "Minerals & Trace Elements" = "矿物质与微量元素",
    "Polyphenols & Flavonoids" = "多酚与黄酮类",
    "Fruits & Vegetables" = "水果与蔬菜",
    "Fermented Foods & Probiotics" = "发酵食品与益生菌",
    "Fatty Acids & Lipids" = "脂肪酸与脂质",
    "Phytoestrogens" = "植物雌激素",
    "Herbal & Botanical" = "草本与植物制品",
    "Other" = "其他",
    "Metabolites & Amino Acids" = "代谢物与氨基酸",
    "Hormones & Endogenous" = "激素与内源性物质"
  ),
  "zh-TW" = c(
    "Carotenoids" = "類胡蘿蔔素",
    "Vitamins A, C, D, E, K" = "維生素 A、C、D、E、K",
    "B Vitamins" = "B群維生素",
    "Antioxidants" = "抗氧化劑",
    "Minerals & Trace Elements" = "礦物質與微量元素",
    "Polyphenols & Flavonoids" = "多酚與類黃酮",
    "Fruits & Vegetables" = "水果與蔬菜",
    "Fermented Foods & Probiotics" = "發酵食品與益生菌",
    "Fatty Acids & Lipids" = "脂肪酸與脂質",
    "Phytoestrogens" = "植物雌激素",
    "Herbal & Botanical" = "草本與植物製品",
    "Other" = "其他",
    "Metabolites & Amino Acids" = "代謝物與胺基酸",
    "Hormones & Endogenous" = "荷爾蒙與內源性物質"
  ),
  "nl" = c(
    "Carotenoids" = "Carotenoïden",
    "Vitamins A, C, D, E, K" = "Vitaminen A, C, D, E en K",
    "B Vitamins" = "B-vitaminen",
    "Antioxidants" = "Antioxidanten",
    "Minerals & Trace Elements" = "Mineralen en sporenelementen",
    "Polyphenols & Flavonoids" = "Polyfenolen en flavonoïden",
    "Fruits & Vegetables" = "Fruit en groenten",
    "Fermented Foods & Probiotics" = "Gefermenteerde voeding en probiotica",
    "Fatty Acids & Lipids" = "Vetzuren en lipiden",
    "Phytoestrogens" = "Fyto-oestrogenen",
    "Herbal & Botanical" = "Kruiden en botanische producten",
    "Other" = "Overig",
    "Metabolites & Amino Acids" = "Metabolieten en aminozuren",
    "Hormones & Endogenous" = "Hormonen en endogene stoffen"
  ),
  "ko" = c(
    "Carotenoids" = "카로티노이드",
    "Vitamins A, C, D, E, K" = "비타민 A, C, D, E, K",
    "B Vitamins" = "비타민 B군",
    "Antioxidants" = "항산화제",
    "Minerals & Trace Elements" = "무기질 및 미량 원소",
    "Polyphenols & Flavonoids" = "폴리페놀 및 플라보노이드",
    "Fruits & Vegetables" = "과일 및 채소",
    "Fermented Foods & Probiotics" = "발효 식품 및 프로바이오틱스",
    "Fatty Acids & Lipids" = "지방산 및 지질",
    "Phytoestrogens" = "식물성 에스트로겐",
    "Herbal & Botanical" = "허브 및 식물성 제품",
    "Other" = "기타",
    "Metabolites & Amino Acids" = "대사산물 및 아미노산",
    "Hormones & Endogenous" = "호르몬 및 내인성 물질"
  )
)

translate_group_label <- function(x, locale = NULL) {
  if (is.null(locale) || !locale %in% names(localized_group_labels)) {
    return(as.character(x))
  }
  labels <- localized_group_labels[[locale]][as.character(x)]
  labels[is.na(labels)] <- as.character(x)[is.na(labels)]
  unname(labels)
}

plot_font_family <- function(locale = NULL) {
  if (is.null(locale) || !locale %in% c("zh-CN", "zh-TW", "ko")) {
    return("sans")
  }

  candidates <- if (locale == "zh-CN") {
    c(
      "Noto Sans CJK SC", "Source Han Sans SC", "PingFang SC",
      "Microsoft YaHei", "Arial Unicode MS"
    )
  } else if (locale == "zh-TW") {
    c(
      "Noto Sans CJK TC", "Source Han Sans TC", "PingFang TC",
      "Microsoft JhengHei", "Arial Unicode MS"
    )
  } else {
    c(
      "Noto Sans CJK KR", "Noto Sans KR", "Source Han Sans K",
      "Apple SD Gothic Neo", "Malgun Gothic", "Arial Unicode MS"
    )
  }

  if (requireNamespace("systemfonts", quietly = TRUE)) {
    available <- unique(systemfonts::system_fonts()$family)
    match <- candidates[candidates %in% available]
    if (length(match) > 0) return(match[[1]])
  }
  "sans"
}

save_plot_pdf <- function(output_path, plot, width, height,
                          locale = NULL, font_family = "") {
  dir.create(dirname(output_path), showWarnings = FALSE, recursive = TRUE)
  if (is.null(locale)) {
    ggsave(
      output_path, plot = plot, width = width, height = height,
      units = "mm", device = "pdf", dpi = 300
    )
  } else {
    localized_device <- if (identical(Sys.info()[["sysname"]], "Darwin")) {
      function(filename, width, height, family = "sans", ...) {
        grDevices::quartz(
          file = filename, type = "pdf", width = width, height = height,
          family = family, ...
        )
      }
    } else {
      grDevices::cairo_pdf
    }
    ggsave(
      output_path, plot = plot, width = width, height = height,
      units = "mm", device = localized_device,
      family = font_family, dpi = 300
    )
  }
}

# =============================================================================
# 1. Read & clean data
# =============================================================================

read_analysis_data <- function(path) {
  if (!is.null(analysis_json)) {
    dataset_key <- if (str_detect(path, "_dietary\\.xlsx$")) "dietary" else "combined"
    disease_key <- case_when(
      str_detect(path, "breast") ~ "breast",
      str_detect(path, "ovarian") ~ "ovarian",
      str_detect(path, "uterine") ~ "uterine"
    )
    raw <- as_tibble(analysis_json[[dataset_key]][[disease_key]])
  } else {
    raw <- read_excel(path)
  }
  if (ncol(raw) != 11) {
    stop("Expected 11 columns in ", path, "; found ", ncol(raw), ".")
  }

  names(raw) <- c(
    "Exposure", "n_studies", "pooled_es_num",
    "ci_low", "ci_high",
    "pi_low", "pi_high",
    "I2", "eggers_p",
    "Total_N", "N_cases"
  )

  raw %>%
    mutate(
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
}

# =============================================================================
# 2. Group mapping, order & colour palettes  (unchanged from original)
# =============================================================================

group_map <- tribble(
  ~Exposure,                  ~Group,
  "eggs",                     "Other",
  "dairy",                    "Other",
  "red_meat",             "Other",
  "fermented_foods",          "Fermented Foods & Probiotics",
  "skyr",                     "Fermented Foods & Probiotics",
  "hemp_seeds",               "Fatty Acids & Lipids",
  "kefir",                    "Fermented Foods & Probiotics",
  "legumes",                  "Fruits & Vegetables",
  "chia_seeds",               "Fatty Acids & Lipids",
  "oats",                     "Other",
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
  "vitamin_a",                "Vitamins A, C, D, E, K",
  "vitamin_b1",               "B Vitamins",
  "mediterranean_diet",       "Other",
  "cod_liver_oil",            "Fatty Acids & Lipids",
  "antioxidants",             "Antioxidants",
  "betaine",                  "Metabolites & Amino Acids",
  "beta-carotene",            "Carotenoids",
  "choline",                  "Metabolites & Amino Acids",
  "magnesium",                "Minerals & Trace Elements",
  "olive",                    "Fruits & Vegetables",
  "vitamin_c",                "Vitamins A, C, D, E, K",
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
  "vitamin_e",                "Vitamins A, C, D, E, K",
  "vitamin_d",                "Vitamins A, C, D, E, K",
  "omega-3_fatty_acids",      "Fatty Acids & Lipids",
  "caffeine",                 "Other",
  "alcohol",                  "Other",
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
  "vitamin_k",                "Vitamins A, C, D, E, K",
  "zinc",                     "Minerals & Trace Elements",
  "carnitine",                "Metabolites & Amino Acids",
  "dehydroepiandrosterone",   "Hormones & Endogenous",
  "cannabidiol",              "Herbal & Botanical",
  "phosphorus",               "Minerals & Trace Elements",
  "ginseng",                  "Herbal & Botanical",
  "vitamin_b3",               "B Vitamins",
  "omega-6_fatty_acids",      "Fatty Acids & Lipids",
  "ginkgo",                   "Herbal & Botanical",
  "coenzyme_q10",             "Antioxidants",
  "sauerkraut",               "Fermented Foods & Probiotics",
  "red_clover",               "Phytoestrogens",
  "black_cohosh",             "Herbal & Botanical",
  "n-acetylcysteine",         "Antioxidants",
  "miso",                     "Fermented Foods & Probiotics",
  "manganese",                "Minerals & Trace Elements",
  "yogurt",                   "Fermented Foods & Probiotics",
  "glucosamine",              "Metabolites & Amino Acids",
  "sage",                     "Herbal & Botanical",
  "pickled_vegetables",       "Fermented Foods & Probiotics",
  "lactobacillus",            "Fermented Foods & Probiotics"
)

group_order <- c(
  "Carotenoids",
  "Vitamins A, C, D, E, K",
  "B Vitamins",
  "Antioxidants",
  "Minerals & Trace Elements",
  "Polyphenols & Flavonoids",
  "Fruits & Vegetables",
  "Fermented Foods & Probiotics",
  "Fatty Acids & Lipids",
  "Phytoestrogens",
  "Herbal & Botanical",
  "Other",
  "Metabolites & Amino Acids",
  "Hormones & Endogenous"
)

group_colors <- c(
  "B Vitamins"               = "#0057B8",
  "Carotenoids"              = "#E55300",
  "Minerals & Trace Elements"= "#007C7C",
  "Fruits & Vegetables"      = "#2E7D32",
  "Vitamins A, C, D, E, K"     = "#C79000",
  "Polyphenols & Flavonoids" = "#6A0DAD",
  "Fermented Foods & Probiotics" = "#00838F",
  "Fatty Acids & Lipids"     = "#B5001F",
  "Phytoestrogens"           = "#7B4A00",
  "Other"                    = "#37474F",
  "Herbal & Botanical"       = "#00695C",
  "Metabolites & Amino Acids"= "#880E4F",
  "Hormones & Endogenous"    = "#4527A0",
  "Antioxidants"             = "#1565C0"
)

group_bg <- c(
  "B Vitamins"               = "#E3EEFA",
  "Carotenoids"              = "#FDEEE6",
  "Minerals & Trace Elements"= "#DFF2F2",
  "Fruits & Vegetables"      = "#E6F4E6",
  "Vitamins A, C, D, E, K"     = "#FBF6E0",
  "Polyphenols & Flavonoids" = "#F2E8FB",
  "Fermented Foods & Probiotics" = "#E0F7FA",
  "Fatty Acids & Lipids"     = "#FBEAED",
  "Phytoestrogens"           = "#F5EDE6",
  "Other"                    = "#ECEFF1",
  "Herbal & Botanical"       = "#E0F2EF",
  "Metabolites & Amino Acids"= "#FCE4EF",
  "Hormones & Endogenous"    = "#EDE7F6",
  "Antioxidants"             = "#E3EEF9"
)

validate_group_map <- function(dat_clean, source_file) {
  missing_group_map <- setdiff(unique(dat_clean$Exposure), group_map$Exposure)
  if (length(missing_group_map) > 0) {
    stop(
      "Missing exposure group mapping for ", source_file, ": ",
      paste(sort(missing_group_map), collapse = ", ")
    )
  }
}

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

translate_exposure_label <- function(x, locale = NULL) {
  english_labels <- prettify_exposure(x)
  if (is.null(locale) || !locale %in% summary_plot_locales) {
    return(english_labels)
  }

  vapply(seq_along(x), function(i) {
    normalized_key <- normalize_translation_key(x[[i]])
    source_label <- unname(translation_source_by_key[normalized_key])
    if (is.null(source_label) || length(source_label) == 0 || is.na(source_label)) {
      stop(
        "Missing Summary exposure translation source for '", x[[i]],
        "' (locale ", locale, ")."
      )
    }
    localized <- translation_catalog[[source_label]][[locale]]
    if (is.null(localized) || length(localized) == 0 || !nzchar(localized[[1]])) {
      stop(
        "Missing Summary exposure translation for '", source_label,
        "' (locale ", locale, ")."
      )
    }
    as.character(localized[[1]])
  }, character(1))
}

# =============================================================================
# 4. Forest plot helpers  (identical logic to original)
# =============================================================================

prepare_dat <- function(dat_clean, dir, locale = NULL) {
  dat_clean %>%
    filter(n_studies > 1) %>%
    left_join(group_map, by = "Exposure") %>%
    mutate(
      Group          = replace_na(Group, "Other"),
      Exposure_label = translate_exposure_label(Exposure, locale),
      Group_label    = translate_group_label(Group, locale),
      Group          = factor(Group, levels = group_order)
    ) %>%
    filter(direction == dir) %>%
    arrange(Group, pooled_es_num) %>%
    mutate(row = row_number())
}

build_plot_rows <- function(df) {
  groups_present <- df %>%
    group_by(Group, Group_label) %>%
    summarise(n = n(), .groups = "drop") %>%
    arrange(match(Group, c(group_order, "Other")))
  
  plot_row   <- integer(nrow(df))
  label_rows <- list()
  current_row <- 1
  
  for (i in seq_len(nrow(groups_present))) {
    grp   <- as.character(groups_present$Group[i])
    n_grp <- groups_present$n[i]
    
    label_rows[[i]] <- tibble(
      plot_row = current_row,
      Group = grp,
      Group_label = groups_present$Group_label[i],
      is_label = TRUE
    )
    current_row <- current_row + 1
    
    idx <- which(as.character(df$Group) == grp)
    plot_row[idx] <- seq(current_row, current_row + n_grp - 1)
    current_row <- current_row + n_grp
  }
  
  df$plot_row <- plot_row
  list(df = df, labels = bind_rows(label_rows), total_rows = current_row - 1)
}

# ---- Table panel ----
make_table_panel <- function(df, label_df, total_rows, title_text, fs = 3.8,
                             font_family = "") {
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
              aes(x = 0.0, y = plot_row, label = str_to_upper(Group_label), color = Group),
              hjust = 0, size = fs - 0.3, fontface = "bold.italic",
              family = font_family, inherit.aes = FALSE) +
    scale_color_manual(values = group_colors, guide = "none") +
    geom_text(data = df,
              aes(x = 0.15, y = plot_row, label = Exposure_label,
                  color = as.character(Group)),
              hjust = 0, size = fs, fontface = "bold", family = font_family,
              inherit.aes = FALSE) +
    geom_text(data = df,
              aes(x = 1.2, y = plot_row, label = as.character(n_studies),
                  color = as.character(Group)),
              hjust = 0.5, size = fs - 0.2, family = font_family,
              inherit.aes = FALSE) +
    geom_text(data = df,
              aes(x = 2.4, y = plot_row, label = N_lab,
                  color = as.character(Group)),
              hjust = 1, size = fs - 0.2, family = font_family,
              inherit.aes = FALSE) +
    geom_text(data = df,
              aes(x = 3.5, y = plot_row, label = Cases_lab,
                  color = as.character(Group)),
              hjust = 1, size = fs - 0.2, family = font_family,
              inherit.aes = FALSE) +
    geom_text(data = df,
              aes(x = 4.7, y = plot_row, label = pooled_ci_lab,
                  color = as.character(Group)),
              hjust = 1, size = fs - 0.2, fontface = "italic", family = font_family,
              inherit.aes = FALSE) +
    annotate("rect",
             xmin = -0.05, xmax = 4.75, ymin = -0.60, ymax = 0.50,
             fill = "#1A1A2E", alpha = 0.93) +
    annotate("text", x = 0.0, y = header_y, label = "Exposure",
             hjust = 0, fontface = "bold", size = fs + 0.5, color = "white",
             family = font_family) +
    annotate("text", x = 1.2, y = header_y, label = "# of studies",
             hjust = 0.5, fontface = "bold", size = fs + 0.5, color = "white",
             family = font_family) +
    annotate("text", x = 2.4, y = header_y, label = "Sample size",
             hjust = 1, fontface = "bold", size = fs + 0.5, color = "white",
             family = font_family) +
    annotate("text", x = 3.5, y = header_y, label = "Cases",
             hjust = 1, fontface = "bold", size = fs + 0.5, color = "white",
             family = font_family) +
    annotate("text", x = 4.7, y = header_y, label = "Pooled RR (95% CI)",
             hjust = 1, fontface = "bold", size = fs + 0.5, color = "white",
             family = font_family) +
    scale_x_continuous(limits = c(-0.05, 4.8), expand = c(0, 0)) +
    scale_y_continuous(limits = y_lim, trans = "reverse", expand = c(0, 0)) +
    labs(title = title_text) +
    theme_void(base_family = font_family) +
    theme(
      plot.title      = element_text(face = "bold", hjust = 0.5, size = 13,
                                     color = "#1A1A2E", margin = margin(b = 8, t = 4)),
      plot.background = element_rect(fill = "white", color = NA),
      plot.margin     = margin(8, 4, 8, 10)
    )
}

# ---- Forest panel ----
make_forest_panel <- function(df, label_df, total_rows, xlim_max = 2.5, fs = 3.8,
                              locale = NULL, font_family = "") {
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
             fontface = "bold", size = fs + 0.5, color = "white",
             family = font_family) +
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
      labels = function(x) translate_group_label(x, locale),
      guide  = guide_legend(
        ncol           = 5,
        override.aes   = list(shape = 15, size = 4.8, alpha = 1),
        title.position = "top",
        title.hjust    = 0,
        byrow          = TRUE
      )
    ) +
    scale_size_continuous(range = c(2.0, 6.5), guide = "none") +
    labs(x = "Pooled RR", y = NULL) +
    theme_minimal(base_size = 11, base_family = font_family) +
    theme(
      axis.text.y      = element_blank(),
      axis.ticks.y     = element_blank(),
      axis.text.x      = element_text(size = 10, color = "#37474F", face = "bold"),
      axis.title.x     = element_text(size = 11, color = "#37474F", margin = margin(t = 6)),
      panel.grid       = element_blank(),
      legend.position  = "bottom",
      legend.text      = element_text(size = 8.2,  color = "#1A1A2E"),
      legend.title     = element_text(size = 9.2, color = "#1A1A2E", face = "bold"),
      legend.key.size  = unit(0.48, "cm"),
      legend.spacing.x = unit(0.28, "cm"),
      legend.margin    = margin(t = 2, r = 0, b = 2, l = 0),
      plot.background  = element_rect(fill = "white", color = NA),
      plot.margin      = margin(8, 16, 8, 2)
    )
}

# ---- Caption ----
make_caption <- function(direction, cancer_label) {
  side <- if (direction == "Protective") {
    paste0("RR < 1 = inversely associated with ", cancer_label, " risk.")
  } else {
    paste0("RR > 1 = positively associated with ", cancer_label, " risk.")
  }
  paste0(
    side, "  |  ",
    "[*] pooled RR (size proportional to # of studies)  |  ",
    "[ ] red outline = statistically significant (95% CI excludes 1.0)  |  ",
    "[*] faded = non-significant  |  dashed line = 95% prediction interval"
  )
}

# ---- Compose & save ----
forest_height_mm <- function(total_rows) {
  # Preserve enough room for the title, legend, and caption while allocating
  # vertical space in proportion to the group and exposure rows actually shown.
  max(105, min(420, 80 + 12 * total_rows))
}

save_forest_figure <- function(dat_clean, direction, cancer_label,
                               title_text, xlim_max, filename,
                               locale = NULL) {
  output_path <- file.path(output_dir, filename)
  font_family <- if (is.null(locale)) "" else plot_font_family(locale)
  df_raw     <- prepare_dat(dat_clean, direction, locale)
  built      <- build_plot_rows(df_raw)
  df         <- built$df
  label_df   <- built$labels
  total_rows <- built$total_rows
  
  tbl        <- make_table_panel(
    df, label_df, total_rows, title_text,
    font_family = font_family
  )
  fst        <- make_forest_panel(
    df, label_df, total_rows, xlim_max,
    locale = locale, font_family = font_family
  )
  legend_grob <- get_legend(fst)
  fst_no_leg  <- fst + theme(legend.position = "none")
  
  caption_grob <- ggdraw() +
    draw_label(make_caption(direction, cancer_label),
               x = 0.01, hjust = 0, size = 7.2,
               color = "#607D8B", fontface = "italic",
               fontfamily = font_family)
  
  combined <- plot_grid(
    plot_grid(tbl, fst_no_leg,
              ncol = 2, rel_widths = c(1.55, 1),
              align = "h", axis = "tb"),
    legend_grob,
    caption_grob,
    ncol        = 1,
    rel_heights = c(1, 0.14, 0.07)
  )
  
  final <- ggdraw(combined) +
    draw_line(x = c(0, 1, 1, 0, 0),
              y = c(0, 0, 1, 1, 0),
              color = "#B0BEC5", linewidth = 0.8)

  figure_height <- forest_height_mm(total_rows)
  
  save_plot_pdf(
    output_path, plot = final, width = 297, height = figure_height,
    locale = locale, font_family = font_family
  )
  message("Saved: ", output_path, " (", total_rows, " rows; ", figure_height, " mm high)")
  invisible(final)
}

# =============================================================================
# 5. Scatter / diagnostic plots  (Plot.R style, adapted for new columns)
#    Two separate functions — one per plot
# =============================================================================

# Shared helper: build the filtered + labelled data frame
build_scatter_df <- function(dat_clean, min_studies = 3, locale = NULL) {
  dat_clean %>%
    filter(
      n_studies >= min_studies,
      is.finite(I2),
      I2 > 0
    ) %>%
    left_join(group_map, by = "Exposure") %>%
    mutate(
      Group          = replace_na(Group, "Other"),
      Group          = factor(Group, levels = group_order),
      exposure_label = translate_exposure_label(Exposure, locale),
      log_eggers_p   = log(eggers_p)   # natural log, same as original
    )
}

# ---- Plot 1: Effect Size vs I² ----
make_es_heterogeneity_plot <- function(dat_clean, min_studies = 3,
                                       filename = "plot_es_vs_heterogeneity.pdf",
                                       cancer_label = NULL,
                                       locale = NULL) {
  output_path <- file.path(output_dir, filename)
  font_family <- if (is.null(locale)) "" else plot_font_family(locale)
  plot_df <- build_scatter_df(dat_clean, min_studies, locale)
  
  p <- ggplot(plot_df,
              aes(x = pooled_es_num, y = I2, color = as.character(Group))) +
    geom_point(aes(size = n_studies), alpha = 0.85) +
    geom_text_repel(
      aes(label = exposure_label), size = 4, fontface = "bold", max.overlaps = 20,
      family = font_family
    ) +
    geom_vline(xintercept = 1, linetype = "dashed") +
    scale_color_manual(values = group_colors, guide = "none") +
    scale_size_continuous(range = c(1, 4), name = "Number of studies") +
    labs(
      title = paste0(
        "Effect Size vs Heterogeneity",
        ifelse(is.null(cancer_label), "", paste0(" - ", str_to_sentence(cancer_label)))
      ),
      x     = "Effect Size (Pooled RR)",
      y     = expression(I^2)
    ) +
    theme_minimal(base_size = 18, base_family = font_family) +
    theme(
      legend.position = "none",
      plot.title      = element_text(face = "bold", size = 19),
      axis.text       = element_text(face = "bold"),
      axis.title      = element_text(face = "bold")
    )
  
  save_plot_pdf(
    output_path, plot = p, width = 210, height = 210,
    locale = locale, font_family = font_family
  )
  message("Saved: ", output_path)
  invisible(p)
}

# ---- Plot 2: log(Egger's p-value) vs I² ----
make_eggers_heterogeneity_plot <- function(dat_clean, min_studies = 3,
                                           filename = "plot_eggers_vs_heterogeneity.pdf",
                                           cancer_label = NULL,
                                           locale = NULL) {
  output_path <- file.path(output_dir, filename)
  font_family <- if (is.null(locale)) "" else plot_font_family(locale)
  plot_df <- build_scatter_df(dat_clean, min_studies, locale) %>%
    filter(!is.na(log_eggers_p), is.finite(log_eggers_p)) %>%
    droplevels()

  groups_present <- group_order[group_order %in% as.character(unique(plot_df$Group))]
  egger_group_colors <- group_colors[names(group_colors) %in% groups_present]

  p <- ggplot(plot_df,
              aes(x = log_eggers_p, y = I2, color = as.character(Group))) +
    geom_point(aes(size = n_studies), alpha = 0.85) +
    geom_text_repel(
      aes(label = exposure_label), size = 4, fontface = "bold", max.overlaps = 20,
      family = font_family
    ) +
    geom_vline(xintercept = log(0.05), linetype = "dashed") +   # log(0.05) ≈ -2.996
    scale_color_manual(values = egger_group_colors, breaks = groups_present,
                       drop = TRUE, guide = "none") +
    scale_size_continuous(range = c(1, 4), name = "Number of studies") +
    labs(
      title = paste0(
        "Egger's Test log(p-value) vs Heterogeneity",
        ifelse(is.null(cancer_label), "", paste0(" - ", str_to_sentence(cancer_label)))
      ),
      x     = "log(Egger's p-value)",
      y     = expression(I^2)
    ) +
    theme_minimal(base_size = 18, base_family = font_family) +
    theme(
      legend.position = "none",
      plot.title      = element_text(face = "bold", size = 19),
      axis.text       = element_text(face = "bold"),
      axis.title      = element_text(face = "bold")
    )
  
  save_plot_pdf(
    output_path, plot = p, width = 210, height = 210,
    locale = locale, font_family = font_family
  )
  message("Saved: ", output_path)
  invisible(p)
}

# =============================================================================
# 6. Render all figures
# =============================================================================

render_args <- commandArgs(trailingOnly = TRUE)
eggers_only <- "--eggers-only" %in% render_args
forests_only <- "--forests-only" %in% render_args
diagnostics_only <- "--diagnostics-only" %in% render_args
locales_only <- "--locales-only" %in% render_args

forest_configs <- tribble(
  ~cancer_label,    ~dataset_label, ~input_file,                                      ~output_suffix,
  "breast cancer",  "combined",    "exposures_meta_analysis_breast_combined.xlsx",   "breast",
  "ovarian cancer", "combined",    "exposures_meta_analysis_ovarian_combined.xlsx",  "ovarian",
  "uterine cancer", "combined",    "exposures_meta_analysis_uterine_combined.xlsx",  "uterine",
  "breast cancer",  "dietary",     "exposures_meta_analysis_breast_dietary.xlsx",    "breast_dietary",
  "ovarian cancer", "dietary",     "exposures_meta_analysis_ovarian_dietary.xlsx",   "ovarian_dietary",
  "uterine cancer", "dietary",     "exposures_meta_analysis_uterine_dietary.xlsx",   "uterine_dietary"
)

if (!eggers_only && !diagnostics_only) {
  for (i in seq_len(nrow(forest_configs))) {
    config <- forest_configs[i, ]
    input_file <- config$input_file[[1]]
    cancer_label <- config$cancer_label[[1]]
    dataset_label <- config$dataset_label[[1]]
    output_suffix <- config$output_suffix[[1]]

    if (!file.exists(input_file)) {
      stop("Required forest-plot input is missing: ", input_file)
    }

    plot_data <- read_analysis_data(input_file)
    validate_group_map(plot_data, input_file)
    analysis_subtitle <- if (dataset_label == "dietary") {
      "\nmeta-analysis of dietary-intake studies"
    } else {
      ""
    }

    if (!locales_only) {
      save_forest_figure(
        dat_clean    = plot_data,
        direction    = "Protective",
        cancer_label = cancer_label,
        title_text   = paste0(
          "Exposures inversely associated with ", cancer_label, " risk",
          analysis_subtitle
        ),
        xlim_max     = 2.2,
        filename     = paste0("forest_protective_", output_suffix, ".pdf")
      )

      save_forest_figure(
        dat_clean    = plot_data,
        direction    = "Harmful",
        cancer_label = cancer_label,
        title_text   = paste0(
          "Exposures positively associated with ", cancer_label, " risk",
          analysis_subtitle
        ),
        xlim_max     = 4.5,
        filename     = paste0("forest_harmful_", output_suffix, ".pdf")
      )
    }

    for (locale in summary_plot_locales) {
      save_forest_figure(
        dat_clean    = plot_data,
        direction    = "Protective",
        cancer_label = cancer_label,
        title_text   = paste0(
          "Exposures inversely associated with ", cancer_label, " risk",
          analysis_subtitle
        ),
        xlim_max     = 2.2,
        filename     = file.path(
          "locales", locale,
          paste0("forest_protective_", output_suffix, ".pdf")
        ),
        locale       = locale
      )

      save_forest_figure(
        dat_clean    = plot_data,
        direction    = "Harmful",
        cancer_label = cancer_label,
        title_text   = paste0(
          "Exposures positively associated with ", cancer_label, " risk",
          analysis_subtitle
        ),
        xlim_max     = 4.5,
        filename     = file.path(
          "locales", locale,
          paste0("forest_harmful_", output_suffix, ".pdf")
        ),
        locale       = locale
      )
    }
  }

}

if (!forests_only) {
  combined_configs <- forest_configs %>% filter(dataset_label == "combined")
  for (i in seq_len(nrow(combined_configs))) {
    config <- combined_configs[i, ]
    input_file <- config$input_file[[1]]
    cancer_label <- config$cancer_label[[1]]
    output_suffix <- config$output_suffix[[1]]
    plot_data <- read_analysis_data(input_file)
    validate_group_map(plot_data, input_file)

    if (!eggers_only) {
      es_filename <- paste0("plot_es_vs_heterogeneity_", output_suffix, ".pdf")
      if (!locales_only) {
        make_es_heterogeneity_plot(
          dat_clean    = plot_data,
          min_studies  = 3,
          filename     = es_filename,
          cancer_label = cancer_label
        )
      }
      for (locale in summary_plot_locales) {
        make_es_heterogeneity_plot(
          dat_clean    = plot_data,
          min_studies  = 3,
          filename     = file.path("locales", locale, es_filename),
          cancer_label = cancer_label,
          locale       = locale
        )
      }
      if (!locales_only && output_suffix == "breast") {
        file.copy(
          file.path(output_dir, es_filename),
          file.path(output_dir, "plot_es_vs_heterogeneity.pdf"),
          overwrite = TRUE
        )
      }
    }

    eggers_filename <- paste0("plot_eggers_vs_heterogeneity_", output_suffix, ".pdf")
    if (!locales_only) {
      make_eggers_heterogeneity_plot(
        dat_clean    = plot_data,
        min_studies  = 3,
        filename     = eggers_filename,
        cancer_label = cancer_label
      )
    }
    for (locale in summary_plot_locales) {
      make_eggers_heterogeneity_plot(
        dat_clean    = plot_data,
        min_studies  = 3,
        filename     = file.path("locales", locale, eggers_filename),
        cancer_label = cancer_label,
        locale       = locale
      )
    }
    if (!locales_only && output_suffix == "breast") {
      file.copy(
        file.path(output_dir, eggers_filename),
        file.path(output_dir, "plot_eggers_vs_heterogeneity.pdf"),
        overwrite = TRUE
      )
    }
  }
}

message(
  if (eggers_only) "Egger figures saved to: " else if (forests_only) "Forest figures saved to: " else if (diagnostics_only) "Diagnostic figures saved to: " else "All figures saved to: ",
  getwd()
)
