import os, json, re

try:
    inp = json.loads(os.environ.get("INPUT_JSON", "{}"))
    user_description = inp.get("user_description", "").strip()
    if not user_description:
        raise ValueError("'user_description' is required and must not be empty.")

    desc_lower = user_description.lower()

    # ── 1. Site purpose & industry ───────────────────────────────────────────
    purpose_keywords = {
        "portfolio": ["portfolio", "showcase", "gallery", "photographer", "photography",
                      "designer", "artist", "creative", "freelance"],
        "e-commerce": ["shop", "store", "ecommerce", "e-commerce", "sell", "product",
                       "marketplace", "retail", "buy"],
        "blog": ["blog", "article", "news", "journal", "magazine", "post"],
        "corporate": ["company", "business", "enterprise", "corporate", "firm",
                      "agency", "consulting", "b2b"],
        "landing-page": ["landing", "launch", "waitlist", "coming soon", "signup",
                         "sign-up", "saas", "app"],
        "nonprofit": ["nonprofit", "non-profit", "charity", "ngo", "foundation",
                      "donation", "volunteer"],
        "restaurant": ["restaurant", "cafe", "coffee", "menu", "food", "bakery",
                       "bistro", "catering"],
        "education": ["school", "course", "tutorial", "education", "learning",
                      "academy", "training", "coaching"],
        "healthcare": ["health", "clinic", "doctor", "medical", "wellness",
                       "therapy", "dental", "hospital"],
        "real-estate": ["real estate", "property", "realty", "homes", "listings",
                        "apartment", "mortgage"],
    }
    site_purpose = "general"
    industry = "general"
    for category, keywords in purpose_keywords.items():
        if any(kw in desc_lower for kw in keywords):
            site_purpose = category
            industry = category
            break

    # ── 2. Target audience ───────────────────────────────────────────────────
    audience_map = {
        "consumers / general public": ["customer", "consumer", "everyone", "public",
                                        "people", "visitors", "users"],
        "businesses / B2B": ["business", "b2b", "company", "enterprise", "client",
                              "corporate", "professional"],
        "students / learners": ["student", "learner", "beginner", "learner",
                                 "education", "course"],
        "creative professionals": ["designer", "photographer", "artist", "creative",
                                    "freelancer"],
        "local community": ["local", "community", "neighborhood", "town", "city"],
    }
    target_audience = "general visitors"
    for audience, keywords in audience_map.items():
        if any(kw in desc_lower for kw in keywords):
            target_audience = audience
            break

    # ── 3. Required pages / sections ─────────────────────────────────────────
    page_map = {
        "home": ["home", "landing", "main", "front page", "hero"],
        "about": ["about", "who we are", "our story", "team", "biography"],
        "services": ["service", "what we do", "offering", "solution"],
        "portfolio": ["portfolio", "gallery", "showcase", "work", "projects",
                       "case stud"],
        "blog": ["blog", "article", "news", "post", "journal"],
        "contact": ["contact", "get in touch", "reach us", "inquiry", "enquiry",
                     "form"],
        "pricing": ["pricing", "price", "plan", "cost", "package", "rate"],
        "shop": ["shop", "store", "product", "cart", "checkout", "buy"],
        "faq": ["faq", "frequently asked", "question"],
        "testimonials": ["testimonial", "review", "feedback", "client say"],
        "team": ["team", "staff", "member", "people", "crew"],
        "menu": ["menu", "food", "dish", "cuisine"],
    }
    required_pages = []
    for page, keywords in page_map.items():
        if any(kw in desc_lower for kw in keywords):
            required_pages.append(page)
    if not required_pages:
        required_pages = ["home", "about", "contact"]
    elif "home" not in required_pages:
        required_pages.insert(0, "home")

    # ── 4. Brand colors / style ──────────────────────────────────────────────
    color_hints = []
    color_names = ["red", "blue", "green", "yellow", "purple", "orange", "pink",
                   "black", "white", "gray", "grey", "gold", "silver", "teal",
                   "navy", "cyan", "magenta", "brown", "beige", "indigo", "violet"]
    hex_pattern = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}\b")
    hex_matches = hex_pattern.findall(user_description)
    color_hints.extend(hex_matches)
    for color in color_names:
        if color in desc_lower:
            color_hints.append(color)

    style_keywords_map = {
        "dark": ["dark", "night", "moody", "dramatic"],
        "light": ["light", "bright", "clean", "airy", "white"],
        "minimal": ["minimal", "minimalist", "simple", "clean", "flat"],
        "bold": ["bold", "vibrant", "colorful", "vivid", "energetic"],
        "elegant": ["elegant", "luxury", "premium", "sophisticated", "upscale",
                    "high-end"],
        "playful": ["playful", "fun", "quirky", "whimsical", "colorful", "kids"],
        "professional": ["professional", "corporate", "formal", "serious",
                          "business"],
        "modern": ["modern", "contemporary", "sleek", "trendy"],
        "vintage": ["vintage", "retro", "classic", "old-school", "nostalgic"],
    }
    style_preferences = []
    for style, keywords in style_keywords_map.items():
        if any(kw in desc_lower for kw in keywords):
            style_preferences.append(style)

    brand_style = {
        "color_hints": color_hints if color_hints else ["to be determined"],
        "style_preferences": style_preferences if style_preferences else ["modern", "clean"],
        "style_references": [],
    }
    url_pattern = re.compile(
        r"https?://[^\s,)\"']+"
        r"|www\.[^\s,)\"']+"
    )
    refs = url_pattern.findall(user_description)
    if refs:
        brand_style["style_references"] = refs

    # ── 5. Copy / content availability ──────────────────────────────────────
    content_ready_kw = ["have content", "have copy", "ready content", "content ready",
                         "copy ready", "i have text", "text ready", "written",
                         "provide content", "send copy"]
    content_needed_kw = ["need copy", "need content", "write content", "generate",
                          "create content", "no content", "don't have", "no copy",
                          "placeholder", "lorem"]
    content_availability = "unknown"
    if any(kw in desc_lower for kw in content_ready_kw):
        content_availability = "client-provided"
    elif any(kw in desc_lower for kw in content_needed_kw):
        content_availability = "ai-generated"

    # ── 6. Deadline / delivery preference ───────────────────────────────────
    deadline_map = {
        "asap": ["asap", "immediately", "today", "right now", "urgent", "rush"],
        "within-a-week": ["week", "7 days", "few days", "this week", "next week"],
        "within-a-month": ["month", "30 days", "few weeks", "this month"],
        "flexible": ["flexible", "no rush", "whenever", "no deadline", "take your time"],
    }
    deadline = "not specified"
    delivery_urgency = "standard"
    for label, keywords in deadline_map.items():
        if any(kw in desc_lower for kw in keywords):
            deadline = label
            delivery_urgency = "urgent" if label == "asap" else "standard"
            break

    # ── Completeness scoring ─────────────────────────────────────────────────
    completeness_flags = {
        "site_purpose_detected": site_purpose != "general",
        "target_audience_detected": target_audience != "general visitors",
        "pages_detected": len(required_pages) > 3,
        "brand_colors_detected": bool(color_hints),
        "style_detected": bool(style_preferences),
        "content_availability_known": content_availability != "unknown",
        "deadline_known": deadline != "not specified",
    }
    completeness_score = round(
        sum(completeness_flags.values()) / len(completeness_flags) * 100
    )
    missing_fields = [k for k, v in completeness_flags.items() if not v]

    requirements = {
        "schema_version": "1.0",
        "site_purpose": site_purpose,
        "industry": industry,
        "target_audience": target_audience,
        "required_pages": required_pages,
        "brand_style": brand_style,
        "content_availability": content_availability,
        "deadline": deadline,
        "delivery_urgency": delivery_urgency,
        "raw_description": user_description,
        "completeness_score": completeness_score,
        "missing_or_inferred_fields": missing_fields,
        "downstream_ready": completeness_score >= 50,
    }

    print(json.dumps(requirements))

except Exception as e:
    print(json.dumps({"error": str(e)}))