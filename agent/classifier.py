"""OpenAI-powered email classification engine with structured output parsing."""

import asyncio
from typing import List, Optional
import openai
from openai import AsyncOpenAI

from models.schemas import Email, EmailClassification, CategoryDefinition
from config.settings import Settings
from config.prompts import build_classification_messages


class EmailClassifier:
    """OpenAI-powered email classifier using structured output parsing."""

    def __init__(self, settings: Settings, categories: List[CategoryDefinition]):
        """
        Initialize email classifier.

        Args:
            settings: Application settings
            categories: List of category definitions
        """
        self.settings = settings
        self.categories = categories

        # Initialize async OpenAI client
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=30.0,
            max_retries=2
        )

    async def classify_email(
        self,
        email: Email,
        include_examples: bool = True
    ) -> Optional[EmailClassification]:
        """
        Classify a single email using OpenAI with structured output.

        Args:
            email: Email to classify
            include_examples: Whether to include few-shot examples

        Returns:
            EmailClassification object or None if classification fails
        """
        try:
            # Build messages for OpenAI
            messages = build_classification_messages(
                email=email,
                categories=self.categories,
                include_examples=include_examples
            )

            # Detect if GPT-5 model
            is_gpt5 = self.settings.openai_model.startswith("gpt-5")

            if is_gpt5:
                # Use /v1/responses for GPT-5 with structured JSON
                # Build input string from messages (combine system + user)
                # Note: GPT-5 Responses API requires "json" in the input for structured output
                input_text = "\n\n".join([
                    f"{msg['role']}: {msg['content']}" 
                    for msg in messages
                ])
                input_text += "\n\nProvide your response as a valid JSON object."
                
                response = await self.client.responses.create(
                    model=self.settings.openai_model,
                    input=input_text,
                    text={
                        "format": {"type": "json_object"},
                        "verbosity": "medium"
                    },
                    reasoning={
                        "effort": "low"
                    },
                    max_output_tokens=self.settings.openai_max_tokens,
                    # No temperature for GPT-5
                )

                # Handle GPT-5 response
                if hasattr(response, 'status') and response.status != "completed":
                    reason = response.incomplete_details.reason if hasattr(response, 'incomplete_details') else "unknown"
                    print(f"Warning: GPT-5 response incomplete: {reason}")
                    return None

                # Parse JSON from output_text
                content = response.output_text if hasattr(response, 'output_text') else ""
                if not content:
                    return None

            else:
                # Standard chat/completions for non-GPT-5
                response = await self.client.chat.completions.parse(
                    model=self.settings.openai_model,
                    messages=messages,
                    response_format=EmailClassification,
                    temperature=self.settings.openai_temperature,
                    max_tokens=self.settings.openai_max_tokens
                )

                content = response.choices[0].message.content
                if not content:
                    return None

            # Parse structured output (common)
            classification = EmailClassification.parse_raw(content)

            # Apply priority boost based on category
            classification = self._apply_priority_boost(classification)

            # Validate category exists
            if not self._validate_category(classification.category):
                print(f"Warning: Invalid category '{classification.category}', using first available")
                classification.category = self.categories[0].name

            return classification

        except openai.APITimeoutError:
            print(f"Timeout classifying email {email.id}")
            return None
        except openai.APIError as e:
            print(f"OpenAI API error classifying email {email.id}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error classifying email {email.id}: {e}")
            return None

    async def classify_batch(
        self,
        emails: List[Email],
        concurrency: int = 5
    ) -> List[tuple[Email, Optional[EmailClassification]]]:
        """
        Classify multiple emails concurrently.

        Args:
            emails: List of emails to classify
            concurrency: Maximum number of concurrent classification tasks

        Returns:
            List of tuples (email, classification)
        """
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(concurrency)

        async def classify_with_semaphore(email: Email) -> tuple[Email, Optional[EmailClassification]]:
            """Classify email with concurrency control."""
            async with semaphore:
                classification = await self.classify_email(email)
                return (email, classification)

        # Process all emails concurrently with limit
        tasks = [classify_with_semaphore(email) for email in emails]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and return results
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Exception classifying email {emails[i].id}: {result}")
                valid_results.append((emails[i], None))
            else:
                valid_results.append(result)

        return valid_results

    def _apply_priority_boost(self, classification: EmailClassification) -> EmailClassification:
        """
        Apply priority boost based on category definition.

        Args:
            classification: Original classification

        Returns:
            Classification with adjusted priority
        """
        # Find category definition
        category_def = next(
            (cat for cat in self.categories if cat.name.lower() == classification.category.lower()),
            None
        )

        if category_def and category_def.priority_boost:
            # Apply boost but clamp to valid range [1, 5]
            new_priority = max(1, min(5, classification.priority + category_def.priority_boost))
            classification.priority = new_priority

        return classification

    def _validate_category(self, category: str) -> bool:
        """
        Validate that category exists in configuration.

        Args:
            category: Category name to validate

        Returns:
            True if category is valid, False otherwise
        """
        return any(
            cat.name.lower() == category.lower()
            for cat in self.categories
        )

    async def close(self) -> None:
        """Close the OpenAI client connection."""
        await self.client.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


class ClassificationCache:
    """Simple cache for email classifications to avoid re-classifying."""

    def __init__(self, max_size: int = 1000):
        """
        Initialize classification cache.

        Args:
            max_size: Maximum number of cached classifications
        """
        self.max_size = max_size
        self.cache: dict[str, EmailClassification] = {}

    def get(self, email_id: str) -> Optional[EmailClassification]:
        """
        Get cached classification for email.

        Args:
            email_id: Email ID

        Returns:
            Cached classification or None
        """
        return self.cache.get(email_id)

    def set(self, email_id: str, classification: EmailClassification) -> None:
        """
        Cache classification for email.

        Args:
            email_id: Email ID
            classification: Classification to cache
        """
        # Simple LRU: remove oldest if cache is full
        if len(self.cache) >= self.max_size:
            # Remove first item (oldest)
            self.cache.pop(next(iter(self.cache)))

        self.cache[email_id] = classification

    def has(self, email_id: str) -> bool:
        """
        Check if email classification is cached.

        Args:
            email_id: Email ID

        Returns:
            True if cached, False otherwise
        """
        return email_id in self.cache

    def clear(self) -> None:
        """Clear all cached classifications."""
        self.cache.clear()


class ClassificationValidator:
    """Validator for classification results."""

    @staticmethod
    def validate_classification(classification: EmailClassification, categories: List[CategoryDefinition]) -> bool:
        """
        Validate classification result.

        Args:
            classification: Classification to validate
            categories: List of valid categories

        Returns:
            True if valid, False otherwise
        """
        # Check category exists
        valid_categories = [cat.name.lower() for cat in categories]
        if classification.category.lower() not in valid_categories:
            return False

        # Check priority in valid range
        if not (1 <= classification.priority <= 5):
            return False

        # Check confidence in valid range
        if not (0.0 <= classification.confidence <= 1.0):
            return False

        # Check reasoning length
        if not (10 <= len(classification.reasoning) <= 500):
            return False

        return True

    @staticmethod
    def sanitize_labels(labels: List[str]) -> List[str]:
        """
        Sanitize label names for email provider compatibility.

        Args:
            labels: List of label names

        Returns:
            Sanitized label names
        """
        sanitized = []
        for label in labels:
            # Convert to lowercase
            clean = label.lower()

            # Replace spaces with hyphens
            clean = clean.replace(" ", "-")

            # Remove special characters except hyphens
            clean = "".join(c for c in clean if c.isalnum() or c == "-")

            # Limit length
            clean = clean[:50]

            if clean:
                sanitized.append(clean)

        return sanitized
