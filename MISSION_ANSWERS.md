> **Student Name:** Ho Bảo Thư  
> **Student ID:** 2A202600352  
> **Date:** 17/4/2026

# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production
### Exercise 1.1: Anti-patterns found

1. API key được hardcode trực tiếp trong source code, nên có nguy cơ bị lộ khi chia sẻ hoặc push repository công khai.  
2. Database credentials cũng được viết cứng trong code, làm tăng rủi ro lộ thông tin truy cập.  
3. Ứng dụng không sử dụng environment variables, vì các cấu hình như `DEBUG` và `MAX_TOKENS` đều nằm trong code.  
4. API key bị in ra bằng `print()`, điều này có thể làm lộ secret trong logs.  
5. Việc sử dụng `print()` thay vì logging chuẩn khiến việc monitor và debug trên cloud kém hiệu quả.  
6. Không có health check endpoint, nên platform khó kiểm tra trạng thái và tự động restart service.  
7. Server được bind vào `localhost`, nên không thể truy cập từ bên ngoài khi deploy trên container hoặc cloud.  
8. Port được cố định là 8000, không phù hợp với môi trường cloud nơi port thường được cấp qua biến môi trường.  
9. `reload=True` được bật, cho thấy cấu hình vẫn mang tính development và không phù hợp cho production.  
10. Endpoint `/ask` không có validation rõ ràng cho input, nên dễ nhận dữ liệu không hợp lệ.  
11. Không có error handling quanh lời gọi model, nên khi có lỗi xảy ra, ứng dụng có thể bị crash.  
12. Không có cơ chế authentication, nên API hoàn toàn mở và có thể bị lạm dụng.  
13. Không có rate limiting để giới hạn số lượng request từ client.  
14. Database URL sử dụng `localhost`, nên sẽ không hoạt động khi deploy lên môi trường cloud.
---

### Exercise 1.3: Comparison table

| Feature              | Develop (Basic)                          | Production (Advanced)                          | Why Important? |
|---------------------|------------------------------------------|-----------------------------------------------|----------------|
| Config  | Hardcode debug, port, settings | Dùng environment variables (`settings`) | Dễ chuyển đổi dev/staging/prod |
| Secrets | Hardcode API key, DB password  | dùng settings                | Tránh lộ thông tin nhạy cảm |
| Logging             | `print()` + log cả secret                | Structured JSON logging, không log secret     | Dễ monitor, tránh leak dữ liệu |
| Request handling    | Query param đơn giản                     | JSON body + validation                        | Chuẩn API, dễ mở rộng |
| Health check        | Không có                                 | `/health`, `/ready`                           | Platform biết khi restart/route traffic |
| Lifecycle           | Không có                                 | Startup / shutdown (lifespan)                 | Quản lý resource đúng cách |
| Shutdown            | Không xử lý                              | Graceful shutdown (SIGTERM)                   | Không mất request đang xử lý |
| CORS                | Không cấu hình                           | Có middleware cấu hình                        | Cho phép frontend gọi API |
| Monitoring          | Gần như không có                         | `/metrics` + structured logs                  | Quan sát hệ thống khi deploy |
| Stability           | Dễ crash                                 | Có validation                  | Tăng độ ổn định hệ thống |
...

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. Base image: python:3.11
2. Working directory: /app
3. COPY requirements.txt trước: Để tận dụng Docker layer cache. Nếu requirements không thay đổi thì Docker không cần cài lại dependencies 
4. CMD vs ENTRYPOINT khác nhau:
- CMD: command mặc định, có thể bị override khi chạy container  
- ENTRYPOINT: command cố định, luôn được chạy, khó override hơn  

### Exercise 2.3: Image size comparison
- Develop: 424MB
- Production: 56.6MB
- Difference: 86.6%

Stage 1:
Cài dependencies và build package với đầy đủ tools.

Stage 2:
Chỉ copy dependencies đã build và code để chạy app.

Image nhỏ hơn:
Không chứa build tools và file tạm nên giảm kích thước đáng kể. Multi-stage build giúp tách biệt môi trường build và runtime, từ đó tối ưu image cho production.

### Exercise 2.4: Docker Compose stack
```markdown
```mermaid
flowchart TD
    C[Client] -->|HTTP 80 / HTTPS 443| N[Nginx - Reverse Proxy]
    N --> A[Agent - FastAPI]
    A --> R[Redis]
    A --> Q[Qdrant]

    subgraph Internal_Docker_Network
        N
        A
        R
        Q
    end

The system starts four services: nginx, agent, redis, and qdrant.

Nginx acts as the entry point and reverse proxy, exposing port 80 to the outside. All client requests are first sent to nginx, which then forwards them to the agent service.

The agent service handles the main application logic. It communicates with Redis for session storage and rate limiting, and with Qdrant as a vector database for retrieval (RAG).

Redis and Qdrant are not exposed externally and only communicate with the agent through an internal network.

This architecture separates concerns and allows the system to scale, since multiple agent instances can be added behind nginx.


## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- URL: https://your-app.railway.app
- Screenshot: [Link to screenshot in repo]

## Part 4: API Security

### Exercise 4.1-4.3: Test results
[Paste your test outputs]

### Exercise 4.4: Cost guard implementation
[Explain your approach]

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
[Your explanations and test results]
```
