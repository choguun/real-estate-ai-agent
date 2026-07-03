"""Supabase adapter (mock + real)."""

from app.adapters.supabase.base import SupabaseAdapter
from app.adapters.supabase.mock import MockSupabaseAdapter
from app.adapters.supabase.real import RealSupabaseAdapter

__all__ = ["SupabaseAdapter", "MockSupabaseAdapter", "RealSupabaseAdapter"]
