from rest_framework.throttling import SimpleRateThrottle


class UserRegisterThrottle(SimpleRateThrottle):
    scope = 'user_register_throttle'

    def get_cache_key(self, request, view):
        # For registration, we should throttle based on IP address
        # as the user is not yet authenticated.
        return self.get_ident(request)