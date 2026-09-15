from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import random
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import pandas as pd
import io
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.getenv('DB_NAME', 'cardinsightpro')
PORT = int(os.getenv('PORT', 8000))
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

# Parse CORS origins
CORS_ORIGINS_STR = os.getenv('CORS_ORIGINS', 'http://localhost:3000')
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(',')]

# Initialize MongoDB
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# FastAPI app
app = FastAPI(title="Corporate Card Analytics API", version="1.0.0")
api_router = APIRouter(prefix="/api")

# Pydantic Models
class Transaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str
    amount: float
    merchant_category: str
    is_international: bool
    transaction_date: datetime
    merchant_name: str

class Customer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    monthly_spend: float
    spend_volatility: float
    international_ratio: float
    payment_timeliness_score: float
    segment: Optional[str] = None
    segment_id: Optional[int] = None
    total_transactions: int = 0
    avg_transaction_value: float = 0
    top_merchant_category: str = ""

class Segment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str
    description: str
    customer_count: int
    avg_monthly_spend: float
    characteristics: Dict[str, Any]

class DashboardStats(BaseModel):
    total_customers: int
    total_spend: float
    avg_spend_per_customer: float
    total_transactions: int
    segment_distribution: List[Dict[str, Any]]

class ProductRecommendation(BaseModel):
    product_name: str
    reason: str
    priority: str
    expected_value: str

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for Render"""
    try:
        await client.admin.command('ping')
        return {"status": "healthy", "environment": ENVIRONMENT}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 503

# API Routes
@api_router.get("/")
async def root():
    return {"message": "Corporate Card Analytics API", "version": "1.0.0"}

async def run_segmentation():
    """Run K-Means clustering on customer data"""
    customers = await db.customers.find({}, {"_id": 0}).to_list(1000)
    
    if len(customers) < 4:
        raise HTTPException(status_code=400, detail="Not enough customers for segmentation (minimum 4)")
    
    df = pd.DataFrame(customers)
    
    # Initialize columns with proper data types
    df['total_transactions'] = 0
    df['avg_transaction_value'] = 0.0
    df['top_merchant_category'] = ""
    
    for idx, customer_id in enumerate(df['id']):
        transactions = await db.transactions.find(
            {"customer_id": customer_id},
            {"_id": 0}
        ).to_list(1000)
        
        if transactions:
            df.at[idx, 'total_transactions'] = int(len(transactions))
            
            avg_value = sum(t['amount'] for t in transactions) / len(transactions)
            df.at[idx, 'avg_transaction_value'] = float(avg_value)
            
            category_counts = {}
            for t in transactions:
                cat = t['merchant_category']
                category_counts[cat] = category_counts.get(cat, 0) + 1
            df.at[idx, 'top_merchant_category'] = max(category_counts, key=category_counts.get) if category_counts else ""
    
    features = ['monthly_spend', 'spend_volatility', 'international_ratio', 'payment_timeliness_score']
    X = df[features].values
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    n_clusters = min(4, len(customers))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df['segment_id'] = kmeans.fit_predict(X_scaled)
    
    segment_names = {
        0: "High-Growth Corporates",
        1: "Travel-Heavy Corporates",
        2: "Low-Engagement / At-Risk",
        3: "Stable Mature Accounts"
    }
    
    segment_means = df.groupby('segment_id')[features].mean()
    
    assigned_names = {}
    for seg_id in range(n_clusters):
        if segment_means.loc[seg_id, 'monthly_spend'] > df['monthly_spend'].median() * 1.5:
            assigned_names[seg_id] = "High-Growth Corporates"
        elif segment_means.loc[seg_id, 'international_ratio'] > df['international_ratio'].median() * 1.3:
            assigned_names[seg_id] = "Travel-Heavy Corporates"
        elif segment_means.loc[seg_id, 'payment_timeliness_score'] < df['payment_timeliness_score'].median() * 0.8:
            assigned_names[seg_id] = "Low-Engagement / At-Risk"
        else:
            assigned_names[seg_id] = "Stable Mature Accounts"
    
    used_names = set()
    final_names = {}
    for seg_id, name in assigned_names.items():
        if name not in used_names:
            final_names[seg_id] = name
            used_names.add(name)
        else:
            for backup_name in segment_names.values():
                if backup_name not in used_names:
                    final_names[seg_id] = backup_name
                    used_names.add(backup_name)
                    break
    
    df['segment'] = df['segment_id'].map(final_names)
    
    for _, row in df.iterrows():
        await db.customers.update_one(
            {"id": row['id']},
            {"$set": {
                "segment": row['segment'],
                "segment_id": int(row['segment_id']),
                "total_transactions": int(row['total_transactions']),
                "avg_transaction_value": float(row['avg_transaction_value']),
                "top_merchant_category": row['top_merchant_category']
            }}
        )
    
    return {"message": "Segmentation completed", "segments_created": n_clusters}

@api_router.get("/data/seed")
@api_router.post("/data/seed")
async def seed_data():
    """Generate synthetic corporate card data"""
    await db.customers.delete_many({})
    await db.transactions.delete_many({})
    
    merchant_categories = [
        "Travel & Transportation", "Hotels & Lodging", "Restaurants",
        "Office Supplies", "Technology & Software", "Professional Services",
        "Marketing & Advertising", "Utilities", "Shipping & Logistics"
    ]
    
    company_names = [
        "TechCorp Solutions", "Global Ventures Ltd", "Innovation Labs Inc",
        "Summit Consulting Group", "Nexus Technologies", "Apex Financial Services",
        "Horizon Enterprises", "Velocity Systems", "Fusion Analytics",
        "Pinnacle Solutions", "Quantum Dynamics", "Stellar Industries"
    ]
    
    customers_data = []
    transactions_data = []
    
    for i in range(150):
        customer_id = str(uuid.uuid4())
        
        base_spend = random.choice([5000, 15000, 30000, 50000, 80000, 120000])
        volatility = random.uniform(0.1, 0.8)
        international_ratio = random.uniform(0, 0.7)
        timeliness = random.uniform(0.6, 1.0)
        
        customer = {
            "id": customer_id,
            "company_name": f"{random.choice(company_names)} {i+1}",
            "monthly_spend": float(base_spend),
            "spend_volatility": float(volatility),
            "international_ratio": float(international_ratio),
            "payment_timeliness_score": float(timeliness),
            "segment": None,
            "segment_id": None,
            "total_transactions": 0,
            "avg_transaction_value": 0.0,
            "top_merchant_category": ""
        }
        customers_data.append(customer)
        
        num_transactions = random.randint(20, 100)
        
        for _ in range(num_transactions):
            amount = abs(np.random.normal(base_spend / num_transactions, base_spend * volatility / num_transactions))
            is_international = random.random() < international_ratio
            
            transaction = {
                "id": str(uuid.uuid4()),
                "customer_id": customer_id,
                "amount": round(amount, 2),
                "merchant_category": random.choice(merchant_categories),
                "is_international": is_international,
                "transaction_date": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 90))).isoformat(),
                "merchant_name": f"{random.choice(['Acme', 'Global', 'Premier', 'Express'])} {random.choice(merchant_categories).split()[0]}"
            }
            transactions_data.append(transaction)
    
    if customers_data:
        await db.customers.insert_many(customers_data)
    if transactions_data:
        await db.transactions.insert_many(transactions_data)
    
    # Run segmentation after seeding
    segmentation_result = await run_segmentation()
    
    return {
        "message": "Data seeded successfully with segmentation",
        "customers_created": len(customers_data),
        "transactions_created": len(transactions_data),
        "segmentation": segmentation_result
    }

@api_router.post("/data/reset-and-seed")
async def reset_and_seed():
    """Reset database and seed fresh data with segmentation"""
    await db.customers.delete_many({})
    await db.transactions.delete_many({})
    
    result = await seed_data()
    return {
        "message": "Database reset and seeded successfully",
        **result
    }

@api_router.post("/analyze")
async def analyze_endpoint():
    """Public endpoint to run segmentation"""
    return await run_segmentation()

@api_router.post("/data/upload-customers")
async def upload_customers(file: UploadFile = File(...)):
    """Upload customers from CSV file"""
    try:
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        
        required_columns = ['company_name', 'monthly_spend', 'spend_volatility', 'international_ratio', 'payment_timeliness_score']
        if not all(col in df.columns for col in required_columns):
            raise HTTPException(status_code=400, detail=f"CSV must contain columns: {', '.join(required_columns)}")
        
        await db.customers.delete_many({})
        
        customers_data = []
        for _, row in df.iterrows():
            customer = {
                "id": str(uuid.uuid4()),
                "company_name": str(row['company_name']),
                "monthly_spend": float(row['monthly_spend']),
                "spend_volatility": float(row['spend_volatility']),
                "international_ratio": float(row['international_ratio']),
                "payment_timeliness_score": float(row['payment_timeliness_score']),
                "segment": None,
                "segment_id": None,
                "total_transactions": 0,
                "avg_transaction_value": 0.0,
                "top_merchant_category": ""
            }
            customers_data.append(customer)
        
        if customers_data:
            await db.customers.insert_many(customers_data)
        
        # Run segmentation after upload
        segmentation_result = await run_segmentation()
        
        return {
            "message": "Customers uploaded and segmented successfully",
            "customers_created": len(customers_data),
            "segmentation": segmentation_result
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

@api_router.post("/data/upload-transactions")
async def upload_transactions(file: UploadFile = File(...)):
    """Upload transactions from CSV file"""
    try:
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        
        required_columns = ['customer_id', 'amount', 'merchant_category', 'is_international', 'transaction_date', 'merchant_name']
        if not all(col in df.columns for col in required_columns):
            raise HTTPException(status_code=400, detail=f"CSV must contain columns: {', '.join(required_columns)}")
        
        await db.transactions.delete_many({})
        
        transactions_data = []
        for _, row in df.iterrows():
            transaction = {
                "id": str(uuid.uuid4()),
                "customer_id": str(row['customer_id']),
                "amount": float(row['amount']),
                "merchant_category": str(row['merchant_category']),
                "is_international": bool(row['is_international']),
                "transaction_date": pd.to_datetime(row['transaction_date']).isoformat(),
                "merchant_name": str(row['merchant_name'])
            }
            transactions_data.append(transaction)
        
        if transactions_data:
            await db.transactions.insert_many(transactions_data)
        
        # Update customer statistics
        await update_customer_statistics()
        
        return {
            "message": "Transactions uploaded successfully",
            "transactions_created": len(transactions_data)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

async def update_customer_statistics():
    """Update customer statistics based on transactions"""
    customers = await db.customers.find({}, {"_id": 0}).to_list(1000)
    
    for customer in customers:
        customer_id = customer['id']
        transactions = await db.transactions.find(
            {"customer_id": customer_id},
            {"_id": 0}
        ).to_list(1000)
        
        if transactions:
            total_transactions = len(transactions)
            avg_transaction_value = sum(t['amount'] for t in transactions) / total_transactions
            
            category_counts = {}
            for t in transactions:
                cat = t['merchant_category']
                category_counts[cat] = category_counts.get(cat, 0) + 1
            top_category = max(category_counts, key=category_counts.get) if category_counts else ""
            
            await db.customers.update_one(
                {"id": customer_id},
                {"$set": {
                    "total_transactions": total_transactions,
                    "avg_transaction_value": float(avg_transaction_value),
                    "top_merchant_category": top_category
                }}
            )

@api_router.get("/data/download-template/{template_type}")
async def download_template(template_type: str):
    """Generate CSV template for download"""
    if template_type == "customers":
        return {
            "columns": ["company_name", "monthly_spend", "spend_volatility", "international_ratio", "payment_timeliness_score"],
            "sample_data": [
                ["Acme Corp", 50000, 0.3, 0.4, 0.9],
                ["TechStart Inc", 30000, 0.5, 0.2, 0.85]
            ],
            "description": {
                "company_name": "Company name (text)",
                "monthly_spend": "Average monthly spend in dollars (number)",
                "spend_volatility": "Spend volatility 0-1 (0.1 = low, 0.8 = high)",
                "international_ratio": "Ratio of international transactions 0-1",
                "payment_timeliness_score": "Payment timeliness score 0-1 (1 = always on time)"
            }
        }
    elif template_type == "transactions":
        return {
            "columns": ["customer_id", "amount", "merchant_category", "is_international", "transaction_date", "merchant_name"],
            "sample_data": [
                ["customer-123", 1500.50, "Travel & Transportation", "true", "2025-01-15", "United Airlines"],
                ["customer-123", 250.00, "Restaurants", "false", "2025-01-14", "Starbucks"]
            ],
            "description": {
                "customer_id": "ID matching a customer (from customers CSV)",
                "amount": "Transaction amount in dollars (number)",
                "merchant_category": "Category (Travel, Hotels, Office Supplies, etc.)",
                "is_international": "true or false",
                "transaction_date": "Date in YYYY-MM-DD format",
                "merchant_name": "Name of merchant"
            }
        }
    else:
        raise HTTPException(status_code=404, detail="Template not found")

@api_router.get("/customers")
async def get_customers(segment: Optional[str] = None):
    """Get all customers with optional segment filter"""
    query = {}
    if segment:
        query["segment"] = segment
    
    customers = await db.customers.find(query, {"_id": 0}).to_list(1000)
    return customers

@api_router.get("/customers/{customer_id}")
async def get_customer(customer_id: str):
    """Get customer details"""
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    transactions = await db.transactions.find(
        {"customer_id": customer_id},
        {"_id": 0}
    ).to_list(1000)
    
    return {
        "customer": customer,
        "transactions": transactions
    }

@api_router.get("/segments")
async def get_segments():
    """Get all segments with statistics"""
    customers = await db.customers.find({}, {"_id": 0}).to_list(1000)
    
    if not customers or not any(c.get('segment') for c in customers):
        return []
    
    df = pd.DataFrame(customers)
    segments_data = []
    
    for segment_name in df['segment'].dropna().unique():
        segment_customers = df[df['segment'] == segment_name]
        
        segment_info = {
            "id": int(segment_customers['segment_id'].iloc[0]) if 'segment_id' in segment_customers.columns and not segment_customers['segment_id'].isna().all() else 0,
            "name": segment_name,
            "description": get_segment_description(segment_name),
            "customer_count": len(segment_customers),
            "avg_monthly_spend": float(segment_customers['monthly_spend'].mean()),
            "characteristics": {
                "avg_spend_volatility": float(segment_customers['spend_volatility'].mean()),
                "avg_international_ratio": float(segment_customers['international_ratio'].mean()),
                "avg_payment_timeliness": float(segment_customers['payment_timeliness_score'].mean())
            }
        }
        segments_data.append(segment_info)
    
    return segments_data

def get_segment_description(segment_name: str) -> str:
    descriptions = {
        "High-Growth Corporates": "Fast-growing companies with high spend and expansion potential",
        "Travel-Heavy Corporates": "Companies with significant international travel and global operations",
        "Low-Engagement / At-Risk": "Accounts showing low engagement or payment issues requiring attention",
        "Stable Mature Accounts": "Established accounts with consistent, predictable spending patterns"
    }
    return descriptions.get(segment_name, "Corporate card customer segment")

@api_router.get("/recommendations/{customer_id}")
async def get_recommendations(customer_id: str):
    """Get beyond-the-card product recommendations"""
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    recommendations = []
    segment = customer.get('segment', '')
    
    if segment == "High-Growth Corporates":
        recommendations = [
            {
                "product_name": "Premium Expense Management Suite",
                "reason": "Automate expense tracking for your growing team",
                "priority": "high",
                "expected_value": "Save 15+ hours/month on expense processing"
            },
            {
                "product_name": "B2B Payment Solutions",
                "reason": "Streamline vendor payments with better cashflow control",
                "priority": "high",
                "expected_value": "Extend payment terms by 30 days"
            },
            {
                "product_name": "Corporate Travel Account",
                "reason": "Dedicated travel booking platform with corporate rates",
                "priority": "medium",
                "expected_value": "Save up to 25% on travel bookings"
            }
        ]
    elif segment == "Travel-Heavy Corporates":
        recommendations = [
            {
                "product_name": "Corporate Travel Account",
                "reason": "Exclusive rates and travel management tools",
                "priority": "high",
                "expected_value": "Save $5,000+ annually on travel costs"
            },
            {
                "product_name": "Global Currency Solutions",
                "reason": "Reduce FX fees on international transactions",
                "priority": "high",
                "expected_value": "Cut currency conversion costs by 40%"
            },
            {
                "product_name": "Travel Insurance Package",
                "reason": "Comprehensive coverage for international business travel",
                "priority": "medium",
                "expected_value": "Full coverage for $50/traveler/month"
            }
        ]
    elif segment == "Low-Engagement / At-Risk":
        recommendations = [
            {
                "product_name": "Basic Expense Management",
                "reason": "Simple tools to improve payment tracking",
                "priority": "medium",
                "expected_value": "Better visibility into spending patterns"
            },
            {
                "product_name": "Payment Automation",
                "reason": "Automate recurring payments to improve timeliness",
                "priority": "high",
                "expected_value": "Never miss a payment deadline"
            },
            {
                "product_name": "Financial Health Dashboard",
                "reason": "Monitor and improve your financial metrics",
                "priority": "medium",
                "expected_value": "Real-time insights into spending health"
            }
        ]
    else:
        recommendations = [
            {
                "product_name": "Advanced Analytics Suite",
                "reason": "Deep insights into spending patterns and optimization",
                "priority": "medium",
                "expected_value": "Identify 10-15% cost savings opportunities"
            },
            {
                "product_name": "B2B Payment Solutions",
                "reason": "Enhance vendor payment efficiency",
                "priority": "medium",
                "expected_value": "Optimize working capital management"
            },
            {
                "product_name": "Expense Management Suite",
                "reason": "Comprehensive expense tracking and reporting",
                "priority": "low",
                "expected_value": "Streamline expense workflows"
            }
        ]
    
    return recommendations

@api_router.get("/dashboard/stats")
async def get_dashboard_stats():
    """Get dashboard statistics"""
    customers = await db.customers.find({}, {"_id": 0}).to_list(1000)
    transactions = await db.transactions.find({}, {"_id": 0}).to_list(10000)
    
    total_spend = sum(c.get('monthly_spend', 0) for c in customers)
    avg_spend = total_spend / len(customers) if customers else 0
    
    segment_dist = {}
    for c in customers:
        seg = c.get('segment', 'Unassigned')
        segment_dist[seg] = segment_dist.get(seg, 0) + 1
    
    segment_distribution = [
        {"name": k, "count": v}
        for k, v in segment_dist.items()
    ]
    
    return {
        "total_customers": len(customers),
        "total_spend": round(total_spend, 2),
        "avg_spend_per_customer": round(avg_spend, 2),
        "total_transactions": len(transactions),
        "segment_distribution": segment_distribution
    }

@api_router.get("/transactions")
async def get_transactions(customer_id: Optional[str] = None):
    """Get all transactions, optionally filtered by customer_id"""
    query = {}
    if customer_id:
        query["customer_id"] = customer_id
    
    transactions = await db.transactions.find(
        query, {"_id": 0}
    ).to_list(10000)
    return transactions

# Include API router
app.include_router(api_router)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if ENVIRONMENT == 'production' else ['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Shutdown event
@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
    logger.info("Database connection closed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PORT,
        reload=(ENVIRONMENT == 'development')
    )
