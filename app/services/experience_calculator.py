"""
Dedicated experience calculation service for HR Console.
Deterministically calculates candidate work experience from employment dates,
merges overlapping employment intervals, handles various date formats,
and provides transparent duration calculations.
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12
}

CURRENT_DATE_KEYWORDS = {
    "present", "current", "currently", "till date", "to date", "now", "ongoing", "today"
}

class ExperienceCalculator:
    """
    Deterministic employment date parser and duration calculator.
    Formula: total_months = (end_year - start_year) * 12 + (end_month - start_month)
    """

    @classmethod
    def parse_date_token(cls, token: str, now: Optional[datetime] = None) -> Optional[Tuple[int, int, bool]]:
        """
        Parses a single date token into (year, month, is_year_only).
        Returns None if parsing fails.
        """
        if not token:
            return None
        t = token.strip().lower()
        if not now:
            now = datetime.now()

        # Check present/current keywords
        if any(kw == t or kw in t for kw in CURRENT_DATE_KEYWORDS):
            return (now.year, now.month, False)

        # Format: YYYY-MM or YYYY/MM
        m_iso = re.match(r'^(\d{4})[-/](\d{1,2})$', t)
        if m_iso:
            y, m = int(m_iso.group(1)), int(m_iso.group(2))
            if 1 <= m <= 12 and 1950 <= y <= 2100:
                return (y, m, False)

        # Format: MM/YYYY or MM-YYYY
        m_num = re.match(r'^(\d{1,2})[-/](\d{4})$', t)
        if m_num:
            m, y = int(m_num.group(1)), int(m_num.group(2))
            if 1 <= m <= 12 and 1950 <= y <= 2100:
                return (y, m, False)

        # Format: Month YYYY (e.g. "June 2023", "Jun 2023", "Jun. 2023", "June, 2023")
        m_mon = re.match(r'^([a-z]+)\.?\s*,?\s*(\d{4})$', t)
        if m_mon:
            mon_str, y_str = m_mon.group(1), m_mon.group(2)
            if mon_str in MONTH_MAP:
                return (int(y_str), MONTH_MAP[mon_str], False)

        # Format: YYYY Month (e.g. "2023 June", "2023 Jun")
        m_mon_rev = re.match(r'^(\d{4})\s*([a-z]+)\.?$', t)
        if m_mon_rev:
            y_str, mon_str = m_mon_rev.group(1), m_mon_rev.group(2)
            if mon_str in MONTH_MAP:
                return (int(y_str), MONTH_MAP[mon_str], False)

        # Format: Day Month YYYY or Month Day YYYY
        m_full = re.search(r'([a-z]+)\.?\s+\d{1,2},?\s+(\d{4})', t)
        if m_full:
            mon_str, y_str = m_full.group(1), m_full.group(2)
            if mon_str in MONTH_MAP:
                return (int(y_str), MONTH_MAP[mon_str], False)

        # Format: Year only (e.g. "2020")
        m_year = re.match(r'^(\d{4})$', t)
        if m_year:
            y = int(m_year.group(1))
            if 1950 <= y <= 2100:
                return (y, 1, True)

        return None

    @classmethod
    def parse_date_range(cls, date_str: str, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Parses a date range string (e.g. "June 2023 – Present", "2020 - 2022", "2022-01 to 2023-01").
        Returns a dict with parsed values or None if invalid.
        """
        if not date_str or not isinstance(date_str, str):
            return None

        # Clean string and standardize range separator without breaking internal hyphens (like YYYY-MM)
        s = re.sub(r'\s+(?:to|till|until)\s+', '<RANGE_SEP>', date_str, flags=re.IGNORECASE)
        s = re.sub(r'\s*[\u2013\u2014\u2212]\s*', '<RANGE_SEP>', s)
        s = re.sub(r'\s+-\s+', '<RANGE_SEP>', s)
        if '<RANGE_SEP>' not in s:
            # Handle unspaced hyphens like "2020-2022" or "06/2023-Present" or "June2023-Present"
            # but do not split internal YYYY-MM
            m = re.search(r'([a-zA-Z0-9/]+(?:\s+[a-zA-Z0-9]+)?)\s*-\s*([a-zA-Z0-9/]+(?:\s+[a-zA-Z0-9]+)?)', s)
            if m:
                s = s[:m.start()] + m.group(1) + '<RANGE_SEP>' + m.group(2) + s[m.end():]

        parts = s.split('<RANGE_SEP>')
        if len(parts) < 2:
            return None

        start_token = parts[0].strip()
        end_token = parts[1].strip()

        start_parsed = cls.parse_date_token(start_token, now=now)
        end_parsed = cls.parse_date_token(end_token, now=now)

        if not start_parsed or not end_parsed:
            return None

        start_year, start_month, start_yr_only = start_parsed
        end_year, end_month, end_yr_only = end_parsed
        is_approximate = start_yr_only or end_yr_only

        # Validation: End date must not precede start date
        if (end_year < start_year) or (end_year == start_year and end_month < start_month):
            return {
                "start_year": start_year,
                "start_month": start_month,
                "end_year": end_year,
                "end_month": end_month,
                "months": 0,
                "is_valid": False,
                "is_approximate": is_approximate,
                "error": "End date precedes start date"
            }

        # Calculate calendar month difference
        total_months = (end_year - start_year) * 12 + (end_month - start_month)

        return {
            "start_year": start_year,
            "start_month": start_month,
            "end_year": end_year,
            "end_month": end_month,
            "months": max(0, total_months),
            "is_valid": True,
            "is_approximate": is_approximate,
            "raw": date_str
        }

    @classmethod
    def format_duration(cls, total_months: int, is_approximate: bool = False) -> str:
        """
        Formats month duration into a clean human-readable label.
        e.g. "3 yrs 4 mos", "2 yrs", "11 mos", "Approximately 2 years"
        """
        if total_months <= 0:
            return "0 mos"

        years = total_months // 12
        months = total_months % 12

        prefix = "Approximately " if is_approximate else ""

        if years > 0 and months > 0:
            if is_approximate:
                return f"{prefix}{years} year{'s' if years != 1 else ''} {months} month{'s' if months != 1 else ''}"
            return f"{years} yr{'s' if years != 1 else ''} {months} mo{'s' if months != 1 else ''}"
        elif years > 0:
            if is_approximate:
                return f"{prefix}{years} year{'s' if years != 1 else ''}"
            return f"{years} yr{'s' if years != 1 else ''}"
        else:
            if is_approximate:
                return f"{prefix}{months} month{'s' if months != 1 else ''}"
            return f"{months} mo{'s' if months != 1 else ''}"

    @classmethod
    def calculate_total_experience(cls, experience_entries: List[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Calculates non-overlapping total professional experience across all employment entries.
        Merges overlapping intervals so concurrent roles are not counted twice.
        Maintains duration at each employer as well as total non-overlapping duration.
        """
        if not now:
            now = datetime.now()

        intervals: List[Tuple[int, int]] = []
        parsed_roles: List[Dict[str, Any]] = []
        has_approximate = False

        for entry in experience_entries:
            date_str = entry.get("dates") or entry.get("date_range") or entry.get("duration") or ""
            parsed = cls.parse_date_range(date_str, now=now)

            employer = entry.get("company") or entry.get("employer") or "Organization"
            role = entry.get("role") or entry.get("title") or "Professional"

            if parsed and parsed.get("is_valid"):
                m_start = parsed["start_year"] * 12 + parsed["start_month"]
                m_end = parsed["end_year"] * 12 + parsed["end_month"]
                dur_months = parsed["months"]
                is_approx = parsed.get("is_approximate", False)
                if is_approx:
                    has_approximate = True

                intervals.append((m_start, m_end))
                parsed_roles.append({
                    "company": employer,
                    "role": role,
                    "dates": date_str,
                    "start_year": parsed["start_year"],
                    "start_month": parsed["start_month"],
                    "end_year": parsed["end_year"],
                    "end_month": parsed["end_month"],
                    "months": dur_months,
                    "duration_display": cls.format_duration(dur_months, is_approx),
                    "is_approximate": is_approx,
                    "is_valid": True
                })
            else:
                parsed_roles.append({
                    "company": employer,
                    "role": role,
                    "dates": date_str or "Unspecified",
                    "months": 0,
                    "duration_display": "Unspecified" if not parsed else "Invalid date range",
                    "is_valid": False,
                    "error": parsed.get("error") if parsed else "Date format not recognized"
                })

        # Merge overlapping intervals
        if not intervals:
            return {
                "total_months": 0,
                "total_years": 0.0,
                "display": "0 mos",
                "is_approximate": False,
                "roles": parsed_roles
            }

        intervals.sort(key=lambda x: (x[0], x[1]))
        merged: List[Tuple[int, int]] = []
        for start, end in intervals:
            if not merged:
                merged.append((start, end))
            else:
                prev_start, prev_end = merged[-1]
                if start <= prev_end:
                    merged[-1] = (prev_start, max(prev_end, end))
                else:
                    merged.append((start, end))

        total_months = sum(end - start for start, end in merged)
        total_years = round(total_months / 12.0, 1)

        display_str = cls.format_duration(total_months, is_approximate=has_approximate)

        return {
            "total_months": total_months,
            "total_years": total_years,
            "display": display_str,
            "is_approximate": has_approximate,
            "roles": parsed_roles
        }

    @classmethod
    def extract_experience_from_text(cls, text: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Scans resume text to detect employment sections, roles, employers, and date ranges.
        Extracts structured experience entries with deterministic date calculations.
        """
        if not text:
            return {
                "total_months": 0,
                "total_years": 0.0,
                "display": "0 mos",
                "roles": []
            }

        if not now:
            now = datetime.now()

        # Regular expression for matching date ranges:
        # e.g. "June 2023 – Present", "06/2023 - Present", "Jan 2020 - Dec 2022", "2020 - 2022"
        date_pattern = re.compile(
            r'('
            r'(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s*,?\s*\d{4}|\d{1,2}/\d{4}|\d{4}-\d{2}|\b\d{4}\b)'
            r'\s*(?:[-–—]|to|till)\s*'
            r'(?:Present|Current|Till\s*Date|To\s*Date|Now|Ongoing|\b\d{4}\b|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s*,?\s*\d{4}|\d{1,2}/\d{4}|\d{4}-\d{2})'
            r')',
            re.IGNORECASE
        )

        entries = []
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue

            matches = list(date_pattern.finditer(line_str))
            for m in matches:
                date_match = m.group(1).strip()
                # Check surrounding lines for company and role
                context = line_str
                company = "Organization"
                role = "Professional"

                # If line contains '|' or '-' or at
                parts = [p.strip() for p in re.split(r'[|\t]+', line_str) if p.strip()]
                for p in parts:
                    if m.group(1) in p:
                        continue
                    if re.search(r'(?:Engineer|Developer|Architect|Lead|Manager|Specialist|Analyst|Consultant|Intern|Director)', p, re.IGNORECASE):
                        role = p
                    elif len(p) > 2 and len(p) < 50:
                        company = p

                # If company or role not found on same line, look at preceding lines
                if company == "Organization" and idx > 0:
                    prev_line = lines[idx - 1].strip()
                    if prev_line and len(prev_line) < 60:
                        company = prev_line

                entries.append({
                    "company": company,
                    "role": role,
                    "dates": date_match
                })

        # Deduplicate identical date ranges for the same company
        seen = set()
        deduped = []
        for e in entries:
            key = f"{e['company'].lower()}::{e['dates'].lower()}"
            if key not in seen:
                seen.add(key)
                deduped.append(e)

        return cls.calculate_total_experience(deduped, now=now)

experience_calculator = ExperienceCalculator()
