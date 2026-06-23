---
name: website-requirements-intake
display_name: "Website Requirements Intake"
description: "Presents a structured questionnaire to gather website requirements and outputs a validated JSON object for downstream skills."
category: productivity
icon: clipboard-list
skill_type: sandbox
catalog_type: addon
tool_schema:
  name: website_requirements_intake
  description: "Collects website requirements from a raw user description by extracting or inferring answers to six key areas and returns a structured JSON requirements object ready for theme-factory, web-artifacts-builder, and gemini-image-gen."
  parameters:
    type: object
    properties:
      user_description:
        type: "string"
        description: "Raw natural-language description of what the user wants built (e.g. 'I need a portfolio site for my photography business, dark theme, needs a gallery and contact page, launching next week')."
    required: [user_description]
---
# Website Requirements Intake
Transforms a raw user description into a validated, structured JSON requirements object covering all six intake dimensions needed to build a website.

## Be Proactive
Call this skill as the very first step whenever a user asks to build, design, or generate a website — before invoking theme-factory, web-artifacts-builder, or gemini-image-gen.