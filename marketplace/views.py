from django.shortcuts import render
from .models import *
from .serializers import *
from accounts.permissions import *
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny
from rest_framework import viewsets
from rest_framework import status
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from rest_framework import filters
from rest_framework.decorators import action
import logging


user = get_user_model()
logger = logging.getLogger(__name__)

# Create your views here.
def success_response(message, data=None, code =status.HTTP_200_OK):
    return Response({
        'success': True,
        'message': message,
        'data': data
    }, status=code)

def error_response(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({
        'success': False,
        'message': message
    }, status=code)

class MarketplaceCategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    permission_classes = [IsOwnerOrReadOnly]

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return success_response("Category list retrieved successfully.", serializer.data)

    def retrieve(self, request, pk=None, *args, **kwargs):
        category = get_object_or_404(Category, pk=pk)
        serializer = self.get_serializer(category)
        return success_response("Category retrieved successfully.", serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return success_response("Category created successfully.", serializer.data, status.HTTP_201_CREATED)

        return error_response("Category creation failed.", serializer.errors)

    def update(self, request, pk=None, *args, **kwargs):
        category = get_object_or_404(Category, pk=pk)
        serializer = self.get_serializer(category, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return success_response("Category updated successfully.", serializer.data)

        return error_response("Category update failed.", serializer.errors)

    def destroy(self, request, pk=None, *args, **kwargs):
        category = get_object_or_404(Category, pk=pk)
        category.delete()
        return success_response("Category deleted successfully.", None, status.HTTP_204_NO_CONTENT)
    
class MarketplaceSubCategoryViewSet(viewsets.ModelViewSet):
    queryset = SubCategory.objects.all()
    serializer_class = SubCategorySerializer
    permission_classes = [IsOwnerOrReadOnly]

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return success_response("SubCategory list retrieved successfully.", serializer.data)
    
    def retrieve(self, request, pk=None, *args, **kwargs):
        subcategory = get_object_or_404(SubCategory, pk=kwargs['pk'])
        serializer = self.get_serializer(subcategory)
        return success_response("SubCategory retrieved successfully.", serializer.data)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success_response("SubCategory created successfully.", serializer.data, status.HTTP_201_CREATED)
        return error_response("SubCategory creation failed.", serializer.errors)
    
    def update(self, request, pk=None, *args, **kwargs):
        subcategory = get_object_or_404(SubCategory, pk=pk)
        serializer = self.get_serializer(subcategory, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success_response("SubCategory updated successfully.", serializer.data)
        return error_response("SubCategory update failed.", serializer.errors)
    
    def destroy(self, request, pk=None, *args, **kwargs):
        subcategory = get_object_or_404(SubCategory, pk=pk)
        subcategory.delete()
        return success_response("SubCategory deleted successfully.", None, status.HTTP_204_NO_CONTENT)
    
class MarketplaceProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['status', 'sub_category', 'sub_category__category']
    search_fields = ['name', 'description', 'location']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductSerializer
    
    def get_queryset(self):
        # Handle Swagger schema generation
        if getattr(self, 'swagger_fake_view', False):
            return Product.objects.none()
        
        queryset = super().get_queryset()
        user = self.request.user
        
        # Admin → show all
        if user.is_staff:
            return queryset
        
        # Show only user's products
        my_products = self.request.query_params.get('my_products', None)
        if my_products:
            return queryset.filter(user=user)
        
        # Show published + own products
        return queryset.filter(Q(status='published') | Q(user=user))

    def list(self, request, *args, **kwargs):
        from datetime import datetime
        import logging
        
        logger = logging.getLogger(__name__)
        
        queryset = self.filter_queryset(self.get_queryset())
        
        # Filter by date range if provided
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        logger.info(f"Product list - start_date: {start_date}, end_date: {end_date}")
        
        if start_date:
            try:
                date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(created_at__date__gte=date_obj)
                logger.info(f"Applied start_date filter: {date_obj}")
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing start_date '{start_date}': {str(e)}")
                pass
        
        if end_date:
            try:
                date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(created_at__date__lte=date_obj)
                logger.info(f"Applied end_date filter: {date_obj}")
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing end_date '{end_date}': {str(e)}")
                pass
        
        serializer = self.get_serializer(queryset, many=True)
        return success_response("Product list retrieved successfully.", serializer.data)

    def retrieve(self, request, pk=None, *args, **kwargs):
        product = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(product)
        return success_response("Product retrieved successfully.", serializer.data)

    def create(self, request, *args, **kwargs):
        try:
            # Check if user can post
            from .models import UserSubscription, PostCredit
            from django.utils import timezone
            
            subscription, _ = UserSubscription.objects.get_or_create(
                user=request.user,
                defaults={'plan': None, 'status': 'active'}
            )
            subscription.reset_monthly_usage()
            
            can_post = subscription.can_post()
            used_credit = False
            
            # Check for available credits if subscription limit reached
            if not can_post:
                credits = PostCredit.objects.filter(
                    user=request.user
                ).exclude(expires_at__lt=timezone.now() if timezone.now() else None)
                
                for credit in credits:
                    if credit.has_credits():
                        credit.use_credit()
                        used_credit = True
                        can_post = True
                        break
            
            if not can_post:
                remaining = subscription.get_remaining_posts()
                return error_response(
                    f"You have reached your posting limit. Remaining posts: {remaining}. "
                    "Please upgrade your plan or purchase additional posts.",
                    status.HTTP_403_FORBIDDEN
                )
            
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                product = serializer.save(user=request.user)
                
                # Increment post count if not using credit
                if not used_credit:
                    subscription.posts_used_this_month += 1
                    subscription.save()
                
                return success_response("Service created successfully.", serializer.data, status.HTTP_201_CREATED)

            return error_response("Service creation failed.", serializer.errors)
        except Exception as e:
            logger.error(f"Error creating service: {str(e)}", exc_info=True)
            return error_response(f"Service creation failed: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, pk=None, *args, **kwargs):
        product = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(product, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return success_response("Product updated successfully.", serializer.data)

        return error_response("Product update failed.", serializer.errors)

    def partial_update(self, request, pk=None, *args, **kwargs):
        product = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(product, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return success_response("Product partially updated successfully.", serializer.data)

        return error_response("Product partial update failed.", serializer.errors)

    def destroy(self, request, pk=None, *args, **kwargs):
        product = get_object_or_404(self.get_queryset(), pk=pk)
        product.delete()
        return success_response("Product deleted successfully.", None, status.HTTP_204_NO_CONTENT)

    # -------- CUSTOM ACTIONS -------- #

    @action(detail=False, methods=['get'])
    def my_products(self, request):
        """Get products created by current user"""
        queryset = self.get_queryset().filter(user=request.user)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return success_response("My products fetched successfully.", serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response("My products fetched successfully.", serializer.data)

    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """Get products by category id"""
        category_id = request.query_params.get('category_id')

        if not category_id:
            return error_response("category_id parameter is required")

        queryset = self.get_queryset().filter(sub_category__category_id=category_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return success_response("Products by category fetched successfully.", serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response("Products by category fetched successfully.", serializer.data)
