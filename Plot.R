setwd('C:/Users/mde4023/Downloads/MetaMamm')
library(readr)
library(ggplot2)
library(dplyr)
library(patchwork)
library(ggrepel)

exposure_results <- read_csv("exposure_results.csv")

relstud=subset(exposure_results,exposure_results$`Number of Studies`>2)


relstud_plot <- relstud %>%
  mutate(
    log_eggers_p = log(`Eggers P-Value`),
    exposure_label = Exposure
  )

p1 <- ggplot(relstud_plot, aes(x = `Effect Size`, y = `I^2`, color = Exposure)) +
  geom_point(aes(size = `Number of Studies`), alpha = 0.85) +
  geom_text_repel(aes(label = exposure_label), size = 3, max.overlaps = 20) +
  labs(
    title = "Effect Size vs Heterogeneity",
    x = "Effect Size",
    y = expression(I^2),
    color = "Exposure",
    size = "Number of studies"
  ) +
  geom_vline(xintercept=1,linetype="dashed")+
  theme_minimal(base_size = 15) +
  theme(
    legend.position = "none",
    plot.title = element_text(face = "bold")
  )

p2 <- ggplot(relstud_plot, aes(x = log_eggers_p, y = `I^2`, color = Exposure)) +
  geom_point(aes(size = `Number of Studies`), alpha = 0.85) +
  geom_text_repel(aes(label = exposure_label), size = 3, max.overlaps = 20) +
  labs(
    title = "Egger's Test log(p-value) vs Heterogeneity",
    x = "log(Egger's p-value)",
    y = expression(I^2),
    color = "Exposure",
    size = "Number of studies"
  ) +
  geom_vline(xintercept=-3,linetype="dashed")+
  theme_minimal(base_size = 15) +
  theme(
    legend.position = "None",
    plot.title = element_text(face = "bold")
  )

p1 + p2 + plot_layout(guides = "collect") &
  theme(legend.position = "none")
log(0.05)

