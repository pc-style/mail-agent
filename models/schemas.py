"""Pydantic models for email data and classification schemas."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr


class EmailProvider(str, Enum):
    """Supported email providers."""
    GMAIL = "gmail"
    OUTLOOK = "outlook"


class Priority(int, Enum):
    """Email priority levels."""
    LOW = 1
    NORMAL = 2
    MODERATE = 3
    HIGH = 4
    CRITICAL = 5


class Email(BaseModel):
    """Email data model."""
    id: str = Field(..., description="Unique email identifier")
    provider: EmailProvider = Field(..., description="Email provider (Gmail/Outlook)")
    subject: str = Field(..., description="Email subject line")
    sender: str = Field(..., description="Sender email address")
    sender_name: Optional[str] = Field(None, description="Sender display name")
    recipient: str = Field(..., description="Recipient email address")
    date: datetime = Field(..., description="Email received date")
    body_preview: str = Field(..., description="Email body preview/snippet")
    body_full: Optional[str] = Field(None, description="Full email body (if available)")
    is_read: bool = Field(False, description="Whether email has been read")
    has_attachments: bool = Field(False, description="Whether email has attachments")
    existing_labels: List[str] = Field(default_factory=list, description="Current labels/categories")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "msg_12345",
                "provider": "gmail",
                "subject": "Your verification code",
                "sender": "noreply@service.com",
                "sender_name": "Service Team",
                "recipient": "user@example.com",
                "date": "2025-01-15T10:30:00Z",
                "body_preview": "Your verification code is 123456",
                "is_read": False,
                "has_attachments": False,
                "existing_labels": ["INBOX"]
            }
        }


class EmailClassification(BaseModel):
    """
    Email classification result from OpenAI.

    This schema is used with OpenAI's structured output parsing
    to ensure consistent classification results.
    """
    category: str = Field(
        ...,
        description="Primary category (e.g., '2fa', 'Work', 'University', 'Receipts', 'AI Projects', 'Personal', 'Newsletter', 'Spam')"
    )
    priority: int = Field(
        ...,
        ge=1,
        le=5,
        description="Priority level from 1 (low) to 5 (critical)"
    )
    labels: List[str] = Field(
        default_factory=list,
        description="Additional labels to apply (e.g., ['urgent', 'action-required', 'finance'])"
    )
    reasoning: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Brief explanation for the classification decision"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence score for the classification (0.0-1.0)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "category": "2fa",
                "priority": 4,
                "labels": ["security", "time-sensitive"],
                "reasoning": "Email contains a verification code and requires immediate attention for authentication purposes.",
                "confidence": 0.95
            }
        }


class CategoryDefinition(BaseModel):
    """Category definition from configuration."""
    name: str = Field(..., description="Category name")
    description: str = Field(..., description="Category description")
    keywords: List[str] = Field(default_factory=list, description="Keywords associated with category")
    priority_boost: int = Field(0, description="Priority adjustment for this category")


class ClassificationConfig(BaseModel):
    """Configuration for email classification."""
    categories: List[CategoryDefinition] = Field(..., description="List of available categories")
    default_priority: int = Field(2, ge=1, le=5, description="Default priority for uncategorized emails")
    auto_apply_labels: bool = Field(True, description="Automatically apply labels to emails")
    create_missing_labels: bool = Field(True, description="Create labels if they don't exist")


class ClassificationResult(BaseModel):
    """Complete classification result including email and classification."""
    email: Email = Field(..., description="Original email data")
    classification: EmailClassification = Field(..., description="Classification result")
    applied_successfully: bool = Field(False, description="Whether labels were applied successfully")
    error: Optional[str] = Field(None, description="Error message if classification failed")
    processed_at: datetime = Field(default_factory=datetime.now, description="When classification was performed")

    class Config:
        json_schema_extra = {
            "example": {
                "email": {
                    "id": "msg_12345",
                    "provider": "gmail",
                    "subject": "Your verification code",
                    "sender": "noreply@service.com",
                    "date": "2025-01-15T10:30:00Z",
                    "body_preview": "Your verification code is 123456"
                },
                "classification": {
                    "category": "2fa",
                    "priority": 4,
                    "labels": ["security"],
                    "reasoning": "Contains verification code",
                    "confidence": 0.95
                },
                "applied_successfully": True,
                "processed_at": "2025-01-15T10:31:00Z"
            }
        }


class BatchClassificationStats(BaseModel):
    """Statistics for a batch classification operation."""
    total_emails: int = Field(0, description="Total emails processed")
    successful: int = Field(0, description="Successfully classified")
    failed: int = Field(0, description="Failed to classify")
    skipped: int = Field(0, description="Skipped (already classified)")
    categories_breakdown: dict[str, int] = Field(
        default_factory=dict,
        description="Count of emails per category"
    )
    average_confidence: float = Field(0.0, description="Average classification confidence")
    processing_time_seconds: float = Field(0.0, description="Total processing time")

    def add_result(self, result: ClassificationResult) -> None:
        """Add a classification result to the statistics."""
        self.total_emails += 1

        if result.applied_successfully:
            self.successful += 1
            category = result.classification.category
            self.categories_breakdown[category] = self.categories_breakdown.get(category, 0) + 1
        elif result.error:
            self.failed += 1
        else:
            self.skipped += 1

    def calculate_average_confidence(self, results: List[ClassificationResult]) -> None:
        """Calculate average confidence from results."""
        confidences = [r.classification.confidence for r in results if r.applied_successfully]
        if confidences:
            self.average_confidence = sum(confidences) / len(confidences)
