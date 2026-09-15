# CardInsightPro Backend - Render Deployment Guide

## Prerequisites
- A Render account (https://render.com)
- MongoDB Atlas account for managed MongoDB (https://www.mongodb.com/cloud/atlas)
- GitHub repository connected to Render

## Step 1: Set Up MongoDB Atlas

1. Go to MongoDB Atlas (https://www.mongodb.com/cloud/atlas)
2. Create a free cluster
3. Create a database user with username and password
4. Whitelist all IPs (0.0.0.0/0) for development, or specific IPs for production
5. Copy the connection string: `mongodb+srv://username:password@cluster.mongodb.net/dbname?retryWrites=true&w=majority`
6. Keep this string safe - you'll need it for Render environment variables

## Step 2: Deploy on Render

### Option A: Using Render Dashboard (Recommended)

1. Go to https://dashboard.render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: `cardinsightpro-backend`
   - **Environment**: Python 3
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: 
     ```
     gunicorn -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --access-logfile - --error-logfile - backend.server:app
     ```
   - **Root Directory**: `./backend`
   - **Plan**: Free (or paid as needed)

5. Add environment variables under "Environment":
   ```
   MONGO_URL=mongodb+srv://username:password@cluster.mongodb.net/cardinsightpro?retryWrites=true&w=majority
   DB_NAME=cardinsightpro
   CORS_ORIGINS=http://localhost:3000,https://your-frontend-url.onrender.com
   ENVIRONMENT=production
   PORT=8000
   ```

6. Click "Create Web Service"

### Option B: Using render.yaml (Infrastructure as Code)

1. Update `render.yaml` with your MongoDB connection string
2. Push to GitHub
3. Go to Render dashboard and link your repository
4. The `render.yaml` will be automatically detected and deployed

## Step 3: Frontend Configuration

Update your React frontend's API endpoint to point to your Render backend:

```javascript
// In your frontend .env file
REACT_APP_API_URL=https://cardinsightpro-backend.onrender.com/api
```

Update `CORS_ORIGINS` in Render environment variables with your frontend URL.

## Step 4: Initialize Database

After deployment, seed the database:

1. Navigate to: `https://your-backend-url.onrender.com/api/data/seed`
2. Or use curl:
   ```bash
   curl -X POST https://your-backend-url.onrender.com/api/data/seed
   ```

## Available Endpoints

- `GET /health` - Health check
- `GET /api/` - API info
- `POST/GET /api/data/seed` - Seed with sample data
- `POST /api/data/reset-and-seed` - Reset and reseed
- `GET /api/customers` - Get all customers
- `GET /api/customers/{customer_id}` - Get specific customer
- `GET /api/segments` - Get customer segments
- `POST /api/data/upload-customers` - Upload customers CSV
- `POST /api/data/upload-transactions` - Upload transactions CSV
- `GET /api/dashboard/stats` - Get dashboard statistics
- `GET /api/transactions` - Get all transactions

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `MONGO_URL` | MongoDB connection string | `mongodb+srv://user:pass@cluster.mongodb.net/db` |
| `DB_NAME` | Database name | `cardinsightpro` |
| `CORS_ORIGINS` | Allowed origins (comma-separated) | `https://frontend.onrender.com` |
| `ENVIRONMENT` | Environment type | `production` or `development` |
| `PORT` | Port number | `8000` |

## Troubleshooting

### Issue: Module not found errors
**Solution**: Ensure all dependencies are in `backend/requirements.txt`

### Issue: MongoDB connection failing
**Solution**: 
1. Check MongoDB Atlas connection string is correct
2. Verify IP whitelist includes Render's IPs
3. Use `mongodb+srv://` protocol (not plain `mongodb://`)

### Issue: CORS errors in frontend
**Solution**: Update `CORS_ORIGINS` environment variable to include your frontend URL

### Issue: Health check failing
**Solution**: 
1. Check logs in Render dashboard
2. Verify MongoDB connection
3. Ensure PORT environment variable is set

### View Logs
In Render dashboard:
1. Click your service
2. Scroll to "Logs" section
3. Filter by type or search for errors

## Performance Tips

- Use Render's paid plans for production with more resources
- Consider using MongoDB Atlas paid tier for production workloads
- Enable auto-scaling if using paid Render plan
- Use CDN for frontend assets

## Security Checklist

- [ ] Use strong MongoDB passwords
- [ ] Enable IP whitelisting in MongoDB Atlas for production
- [ ] Use HTTPS URLs in CORS_ORIGINS
- [ ] Set `ENVIRONMENT=production`
- [ ] Rotate API keys and secrets regularly
- [ ] Keep dependencies updated

## Deployment Automation

For automatic deployments on git push:
1. Push to your GitHub repository
2. Render automatically rebuilds and deploys (if configured)
3. Monitor deployment in Render dashboard

## Next Steps

1. Set up frontend deployment on Vercel or Netlify
2. Configure proper CORS between frontend and backend
3. Set up monitoring and alerting
4. Document your API endpoints for team members
