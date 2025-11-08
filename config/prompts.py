"""Prompt templates for email classification using OpenAI."""

from typing import List
from models.schemas import Email, CategoryDefinition


def build_system_prompt(categories: List[CategoryDefinition]) -> str:
    """
    Build system prompt for email classification (optimized for GPT-4o-mini).

    Args:
        categories: List of category definitions

    Returns:
        Formatted system prompt
    """
    categories_text = "\n".join([
        f"- {cat.name.upper()}: {cat.description}"
        for cat in categories
    ])

    keywords_text = "\n".join([
        f"  {cat.name}: {', '.join(cat.keywords) if cat.keywords else 'N/A'}"
        for cat in categories
    ])

    # build exact category names list for reference
    category_names = [cat.name for cat in categories]
    category_names_text = ", ".join([f'"{name}"' for name in category_names])

    prompt = f"""You are an expert email classifier. Classify emails quickly and accurately.

## Available Categories (USE EXACT NAMES):

{category_names_text}

## Category Details

{categories_text}

## Keywords Reference

{keywords_text}

## Priority Scale

1=Low (newsletters), 2=Normal (regular), 3=Moderate (action soon), 4=High (urgent), 5=Critical (immediate)

## Classification Rules

- **Security & 2FA**: Priority 4-5. Verification codes, password resets, security alerts, 2FA codes.
- **Work & Projects**: Priority 2-4. Meetings, projects, professional communication, work updates, team discussions.
- **Finance & Receipts**: Priority 1-3. Invoices, payment confirmations, bank statements, expense reports, receipts.
- **Shipping & Delivery**: Priority 1-3. Order confirmations, shipping notifications, tracking information.
- **University/Academia**: Priority 2-4. Academic courses, assignments, university announcements, course materials.
- **Personal & Social**: Priority 1-2. Friends, family, casual personal communication, social events.
- **Newsletters & Reading**: Priority 1. Subscriptions, weekly digests, newsletters, informative content, reading material.
- **Promotions & Junk**: Priority 1. Marketing emails, advertisements, spam, promotional content.

## How to Classify

1. Identify the MOST appropriate single category from the exact list above
2. Set priority 1-5 based on urgency
3. Add 0-3 descriptive labels (lowercase, hyphenated)
4. Brief reasoning: 1-2 sentences, 10-500 chars
5. Confidence: 0.5-1.0

## Key Signals

- Sender (domain, noreply, company name)
- Subject keywords (urgent, verify, meeting, etc.)
- Body urgency (expires, immediate, confirm, etc.)
- Time sensitivity (deadline, today, expire time)
- Action needed (click, approve, respond, confirm)

## Examples

**Example 1:** "Your verification code: 123456"
→ "Security & 2FA", Priority 5, ["security", "time-sensitive"], Confidence 0.97
"Security verification code requiring immediate action before expiration."

**Example 2:** "Weekly digest - Technology news"
→ "Newsletters & Reading", Priority 1, ["read-later"], Confidence 0.96
"Newsletter subscription with informational non-urgent content."

**Example 3:** "Meeting rescheduled to Tuesday"
→ "Work & Projects", Priority 3, ["meeting"], Confidence 0.93
"Work meeting change requiring calendar update."

**Example 4:** "Your Amazon order has shipped"
→ "Shipping & Delivery", Priority 2, ["tracking"], Confidence 0.94
"Order shipment confirmation with tracking information."

## CRITICAL: Category Name Rules

- You MUST use one of these EXACT category names (case-sensitive, including spaces and special characters):
  {category_names_text}
- Do NOT use shortened names like "2fa", "Newsletter", "Work", "Receipts"
- Do NOT invent new category names
- If unsure, choose the closest match from the list above

## Important

- Use EXACT category names from the list above (case-sensitive)
- Priority: integer 1-5
- Confidence: decimal 0.5-1.0
- Return VALID JSON only"""

    return prompt


def build_user_prompt(email: Email) -> str:
    """
    Build user prompt with email content for classification.

    Args:
        email: Email object to classify

    Returns:
        Formatted user prompt
    """
    sender_info = f"{email.sender_name} <{email.sender}>" if email.sender_name else email.sender
    attachments_info = " [Has attachments]" if email.has_attachments else ""
    existing_labels_info = f"\nLabels: {', '.join(email.existing_labels)}" if email.existing_labels else ""

    body = email.body_full if email.body_full else email.body_preview

    prompt = f"""Classify this email:

**Subject:** {email.subject}
**From:** {sender_info}
**Date:** {email.date.strftime('%Y-%m-%d %H:%M:%S')}{attachments_info}{existing_labels_info}

**Body:**
{body}

---

Analyze and classify. Return JSON with: category, priority, labels, reasoning, confidence."""

    return prompt


def build_few_shot_examples() -> List[dict]:
    """
    Build few-shot examples for improved classification accuracy.

    Returns:
        List of example message pairs (user, assistant)
    """
    examples = [
        {
            "user": """Classify this email:

**Subject:** Your Amazon order #123-4567890 has shipped
**From:** Amazon <shipment-tracking@amazon.com>
**Date:** 2025-01-15 09:23:15

**Body:**
Your order has been shipped and will arrive by January 18.

Track your package: [link]

Order: Wireless Mouse ($25.99), USB-C Cable ($12.99)""",
            "assistant": """{
    "category": "Shipping & Delivery",
    "priority": 2,
    "labels": ["shopping", "tracking"],
    "reasoning": "Order shipment confirmation with tracking info. Standard shipping notification, no immediate action needed.",
    "confidence": 0.94
}"""
        },
        {
            "user": """Classify this email:

**Subject:** Your verification code: 987654
**From:** no-reply@google.com
**Date:** 2025-01-15 14:22:11

**Body:**
Your Google verification code is: 987654
This code expires in 10 minutes.""",
            "assistant": """{
    "category": "Security & 2FA",
    "priority": 5,
    "labels": ["security", "time-sensitive"],
    "reasoning": "Time-sensitive security verification code requiring immediate action before expiration.",
    "confidence": 0.99
}"""
        },
        {
            "user": """Classify this email:

**Subject:** Weekly Tech Digest - Issue #42
**From:** newsletter@techblog.com
**Date:** 2025-01-15 16:45:00

**Body:**
Here's this week's roundup of technology news and updates for your reading.""",
            "assistant": """{
    "category": "Newsletters & Reading",
    "priority": 1,
    "labels": ["read-later"],
    "reasoning": "Regular newsletter subscription with non-urgent informational content for leisure reading.",
    "confidence": 0.97
}"""
        }
    ]

    return examples


def build_classification_messages(
    email: Email,
    categories: List[CategoryDefinition],
    include_examples: bool = True
) -> List[dict]:
    """
    Build complete message array for OpenAI chat completion.

    Args:
        email: Email to classify
        categories: List of category definitions
        include_examples: Whether to include few-shot examples

    Returns:
        List of message dictionaries for OpenAI API
    """
    messages = [
        {
            "role": "system",
            "content": build_system_prompt(categories)
        }
    ]

    # Add few-shot examples for better accuracy
    if include_examples:
        examples = build_few_shot_examples()
        for example in examples:
            messages.append({"role": "user", "content": example["user"]})
            messages.append({"role": "assistant", "content": example["assistant"]})

    # Add the actual email to classify
    messages.append({
        "role": "user",
        "content": build_user_prompt(email)
    })

    return messages
