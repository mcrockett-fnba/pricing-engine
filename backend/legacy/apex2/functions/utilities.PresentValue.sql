SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE   FUNCTION [utilities].[PresentValue](@paymentAmount DECIMAL(15, 2), @ratePerPeriod NUMERIC(10,7), @periods INT)
RETURNS DECIMAL(15, 2)
AS 
BEGIN;

RETURN ISNULL(@paymentAmount * (1 - POWER(1 / (1 + @ratePerPeriod), @periods)) / NULLIF(@ratePerPeriod, 0.00), 0.00);

END;
GO