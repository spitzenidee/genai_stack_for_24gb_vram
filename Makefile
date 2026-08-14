# genai_stack — GPU work-mode switcher
#
# Modes are mutually exclusive on the eGPU (no VRAM isolation between
# contexts): llama | comfyui | gromacs | blender.
# llamacpp-igpu runs on the iGPU and is started in llama/comfyui modes;
# it does not contend for eGPU VRAM.
# Always-on regardless of mode: lact, gpu-exporter, otel-collector, llama-sd.

MAKEFILE_DIR := $(dir $(realpath $(firstword $(MAKEFILE_LIST))))
SWITCH := $(MAKEFILE_DIR)scripts/switch-mode.sh

.DEFAULT_GOAL := help

.PHONY: help llama comfyui gromacs blender status

help:
	@echo "genai_stack — GPU work modes (mutually exclusive on eGPU: llama | comfyui | gromacs | blender)"
	@echo
	@echo "  make llama     switch to Llama mode (llamacpp-egpu, llamacpp-igpu, open-webui)"
	@echo "  make comfyui   switch to ComfyUI mode (comfyui-rocm, llamacpp-igpu)"
	@echo "  make gromacs   switch to GROMACS mode (interactive, docker compose exec in)"
	@echo "  make blender   switch to Blender mode (interactive, docker compose exec in)"
	@echo "  make status    show current mode + container states"
	@echo
	@$(MAKE) --no-print-directory status

llama:
	@$(SWITCH) llama

comfyui:
	@$(SWITCH) comfyui

gromacs:
	@$(SWITCH) gromacs

blender:
	@$(SWITCH) blender

status:
	@docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
