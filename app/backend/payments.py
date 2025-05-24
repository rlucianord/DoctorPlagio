import stripe
import sys
from pathlib import Path
sys.path[0] = str(Path(sys.path[0]).parent)
print(sys.path[1])
from backend.config import STRIPE_SECRET_KEY
from sqlalchemy.orm import Session
from backend import  models,schemas
from datetime import datetime, timedelta

stripe.api_key = STRIPE_SECRET_KEY

# Ejemplo básico de creación de una suscripción
def create_stripe_subscription(customer_id, price_id,response_model="None"):
    try:
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id}],
        )
        return subscription
    except stripe.error.StripeError as e:
        print(f"Error al crear la suscripción en Stripe: {e}")
        return None

# Ejemplo básico de obtención de la información de un cliente de Stripe
def get_stripe_customer(customer_id):
    try:
        customer = stripe.Customer.retrieve(customer_id)
        return customer
    except stripe.error.StripeError as e:
        print(f"Error al obtener el cliente de Stripe: {e}")
        return None

# ... (Más funciones para gestionar pagos, cancelar suscripciones, etc.)

def update_user_subscription(db: Session, user: models.User, subscription_data):
    # Lógica para actualizar la base de datos local con la información de la suscripción
    subscription = models.Subscription(
        user_id=user.id,
        plan_name=subscription_data.get("plan_name", "basic"),
        start_date=datetime.fromtimestamp(subscription_data["current_period_start"]),
        end_date=datetime.fromtimestamp(subscription_data["current_period_end"]),
        status=subscription_data["status"]
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription