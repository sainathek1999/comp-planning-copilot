from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True)
    role = Column(String, nullable=False)
    level = Column(String, nullable=False)       # L3, L4, L5, L6
    location = Column(String, nullable=False)    # San Francisco, New York, Austin, Remote
    current_salary = Column(Float, nullable=False)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    department = Column(String)

    proposals = relationship("Proposal", foreign_keys="Proposal.employee_id", back_populates="employee")
    ratings = relationship("Rating", back_populates="employee")


class PayBand(Base):
    __tablename__ = "pay_bands"

    id = Column(Integer, primary_key=True)
    role = Column(String, nullable=False)
    level = Column(String, nullable=False)
    location = Column(String, nullable=False)
    min_salary = Column(Float)
    mid_salary = Column(Float)
    max_salary = Column(Float)


class BudgetPool(Base):
    __tablename__ = "budget_pools"

    id = Column(Integer, primary_key=True)
    manager_id = Column(Integer, ForeignKey("employees.id"))
    cycle_id = Column(String, default="2026-H1")
    total_budget = Column(Float)
    allocated_budget = Column(Float, default=0.0)

    manager = relationship("Employee", foreign_keys=[manager_id])


class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    cycle_id = Column(String, default="2026-H1")
    rating = Column(String)   # "Exceeds", "Meets", "Below"

    employee = relationship("Employee", back_populates="ratings")


class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    manager_id = Column(Integer, ForeignKey("employees.id"))
    cycle_id = Column(String, default="2026-H1")
    current_salary = Column(Float)
    proposed_salary = Column(Float)
    increase_pct = Column(Float)
    status = Column(String, default="pending")   # pending, approved, rejected, escalated
    equity_flagged = Column(Integer, default=0)  # 0/1 bool
    notes = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee", foreign_keys=[employee_id], back_populates="proposals")
    manager = relationship("Employee", foreign_keys=[manager_id])
